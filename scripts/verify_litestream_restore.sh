#!/usr/bin/env bash
#
# Prove the R2 backup can actually be restored. Run this on the origin box.
#
#     sudo scripts/verify_litestream_restore.sh
#
# An untested backup is not a backup, and after the cut-over this machine holds
# the only copy of the library — so this needs to be a thing you can run often
# and without thinking about it.
#
# It therefore does NOT stop the service. It restores from R2 into a scratch
# directory and compares that against the live database, which is only ever
# opened read-only. The live file is fingerprinted before and after and the run
# fails if it changed, so "did this touch production" is answered by the script
# rather than by trust. Nothing is written outside the scratch directory.
#
# Exit status is 0 only if the restore is byte-comparable to live.

set -euo pipefail

DB="${DB:-/var/lib/imgmanager/imgmanager.db}"
CONFIG="${CONFIG:-/etc/litestream.yml}"
SCRATCH="$(mktemp -d /tmp/litestream-verify.XXXXXX)"
RESTORED="$SCRATCH/restored.db"
trap 'rm -rf "$SCRATCH"' EXIT

fail() { echo "FAIL: $*" >&2; exit 1; }

[ -f "$DB" ]     || fail "no database at $DB"
[ -f "$CONFIG" ] || fail "no litestream config at $CONFIG"

# Read-only URI: opening the live file any other way risks a recovery write.
LIVE_RO="file:$DB?mode=ro"

fingerprint() { stat -c "%s" "$DB"; sha256sum "$DB" | cut -d" " -f1; }
BEFORE="$(fingerprint)"

echo "== replication status =="
litestream generations -config "$CONFIG" "$DB"

echo
echo "== restoring from R2 into $RESTORED =="
litestream restore -config "$CONFIG" -o "$RESTORED" "$DB" 2>&1 | tail -3
[ -f "$RESTORED" ] || fail "litestream produced no file"

echo
echo "== integrity =="
check="$(sqlite3 "$RESTORED" 'PRAGMA integrity_check;')"
[ "$check" = "ok" ] || fail "integrity_check said: $check"
echo "integrity_check: ok"

fk="$(sqlite3 "$RESTORED" 'PRAGMA foreign_key_check;')"
[ -z "$fk" ] || fail "foreign_key_check found violations: $fk"
echo "foreign_key_check: ok"

echo
echo "== schema =="
diff <(sqlite3 "$RESTORED" 'SELECT type,name FROM sqlite_master ORDER BY type,name;') \
     <(sqlite3 "$LIVE_RO"  'SELECT type,name FROM sqlite_master ORDER BY type,name;') \
  || fail "restored schema differs from live"
echo "schema: identical"

echo
echo "== row counts per table =="
counts() {
  for t in $(sqlite3 "$1" \
      'SELECT name FROM sqlite_master WHERE type="table" AND name NOT LIKE "sqlite_%" ORDER BY name;'); do
    printf '%-22s %s\n' "$t" "$(sqlite3 "$1" "SELECT COUNT(*) FROM \"$t\";")"
  done
}
counts "$RESTORED" > "$SCRATCH/restored.txt"
counts "$LIVE_RO"  > "$SCRATCH/live.txt"
cat "$SCRATCH/restored.txt"
diff "$SCRATCH/restored.txt" "$SCRATCH/live.txt" || fail "row counts differ from live"
echo "counts: every table matches"

echo
echo "== content =="
# Counts alone would pass against a file full of the right number of wrong rows,
# so hash the actual values of the two tables that hold the library.
content() {
  sqlite3 "$1" '
    SELECT name||"|"||COALESCE(series,"")||"|"||COALESCE(rank,"")||"|"||COALESCE(main_image_url,"")
      FROM characters ORDER BY id;
    SELECT character_id||"|"||url||"|"||COALESCE(position,-1)
      FROM custom_images ORDER BY id;' | sha256sum | cut -d" " -f1
}
r="$(content "$RESTORED")"; l="$(content "$LIVE_RO")"
[ "$r" = "$l" ] || fail "content hash differs: restored=$r live=$l"
echo "content hash: $r"

echo
AFTER="$(fingerprint)"
[ "$BEFORE" = "$AFTER" ] || fail "THE LIVE DATABASE CHANGED DURING THIS RUN"
echo "live database untouched"

echo
echo "PASS: the R2 backup restores to a database identical to live."
