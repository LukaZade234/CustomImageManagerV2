#!/usr/bin/env bash
# Pull the latest main and restart the API, rolling back if it fails to come up.
#
# Safe to run unattended from a systemd timer: it exits immediately when there is
# nothing new, refuses to run twice at once, and never leaves the site down --
# if the new commit fails its health check, it returns to the previous one.
#
# Run as root (systemd does):  sudo /opt/imgmanager/deploy/update.sh

set -uo pipefail

APP_DIR="${APP_DIR:-/opt/imgmanager}"
APP_USER="${APP_USER:-imgmanager}"
SERVICE="${SERVICE:-imgmanager}"
HEALTH_URL="${HEALTH_URL:-http://localhost:8080/api/health}"
BRANCH="${BRANCH:-main}"
UV="${UV:-/usr/local/bin/uv}"

log() { echo "[$(date -Is)] $*"; }

# One deploy at a time. The timer could otherwise fire again mid-run.
exec 9>/var/lock/imgmanager-update.lock
if ! flock -n 9; then
    log "another update is already running; skipping"
    exit 0
fi

as_app() { sudo -u "$APP_USER" -H git -C "$APP_DIR" "$@"; }

health_ok() {
    for _ in $(seq 1 15); do
        sleep 2
        if curl -fsS -m 5 "$HEALTH_URL" >/dev/null 2>&1; then
            return 0
        fi
    done
    return 1
}

as_app fetch --quiet origin "$BRANCH" || { log "ERROR: git fetch failed"; exit 1; }

LOCAL=$(as_app rev-parse HEAD)
REMOTE=$(as_app rev-parse "origin/$BRANCH")

if [ "$LOCAL" = "$REMOTE" ]; then
    exit 0            # nothing to do; stay quiet so the journal is not noise
fi

log "updating ${LOCAL:0:8} -> ${REMOTE:0:8}"

LOCK_BEFORE=$(sha256sum "$APP_DIR/uv.lock" 2>/dev/null | cut -d' ' -f1)

# --ff-only rather than reset --hard: if the server has somehow diverged, stop
# and say so instead of silently destroying whatever is there.
if ! as_app merge --ff-only "origin/$BRANCH"; then
    log "ERROR: cannot fast-forward. The server working tree has diverged."
    log "Inspect it by hand; refusing to clobber local state."
    exit 1
fi

LOCK_AFTER=$(sha256sum "$APP_DIR/uv.lock" 2>/dev/null | cut -d' ' -f1)
if [ "$LOCK_BEFORE" != "$LOCK_AFTER" ]; then
    log "uv.lock changed; syncing dependencies"
    if ! sudo -u "$APP_USER" -H "$UV" sync --locked --no-dev --directory "$APP_DIR"; then
        log "ERROR: dependency sync failed; rolling back"
        as_app reset --hard "$LOCAL" --quiet
        sudo -u "$APP_USER" -H "$UV" sync --locked --no-dev --directory "$APP_DIR" || true
        systemctl restart "$SERVICE"
        exit 1
    fi
fi

systemctl restart "$SERVICE"

if health_ok; then
    log "deployed ${REMOTE:0:8} successfully"
    exit 0
fi

# The new commit does not serve traffic. Go back to the one that did rather than
# leaving the site down until somebody notices.
log "ERROR: health check failed after deploying ${REMOTE:0:8}; rolling back to ${LOCAL:0:8}"
as_app reset --hard "$LOCAL" --quiet
if [ "$LOCK_BEFORE" != "$LOCK_AFTER" ]; then
    sudo -u "$APP_USER" -H "$UV" sync --locked --no-dev --directory "$APP_DIR" || true
fi
systemctl restart "$SERVICE"

if health_ok; then
    log "rollback to ${LOCAL:0:8} succeeded; site is up on the previous commit"
else
    log "CRITICAL: rollback also failed health check. Manual intervention needed."
fi
exit 1
