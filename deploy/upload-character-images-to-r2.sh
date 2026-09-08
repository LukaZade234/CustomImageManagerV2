#!/usr/bin/env bash
# Upload the ~1000 default character images to Cloudflare R2.
#
# These are currently served by Flask off local disk, which means every one of
# them crosses the ocean from a single origin. On R2 behind a custom domain they
# come from Cloudflare's edge instead, which is most of the answer to "users on
# the other side of the world".
#
# Needs rclone with an R2 remote. `wrangler r2 object put` uploads one file per
# invocation and would take an age for a thousand of them.
#
#   rclone config create r2 s3 \
#     provider=Cloudflare \
#     access_key_id=<R2_ACCESS_KEY_ID> \
#     secret_access_key=<R2_SECRET_ACCESS_KEY> \
#     endpoint=https://<CLOUDFLARE_ACCOUNT_ID>.r2.cloudflarestorage.com \
#     acl=private
#
# Then point VITE_IMAGE_BASE_URL at the bucket's custom domain and rebuild the
# frontend. The frontend appends /character_images/<file>, so the objects must
# live under that prefix.

set -euo pipefail

BUCKET="${R2_BUCKET:-imgmanager-assets}"
REMOTE="${RCLONE_REMOTE:-r2}"
SRC="$(cd "$(dirname "$0")/.." && pwd)/character_images"

if [ ! -d "$SRC" ]; then
    echo "No character_images directory at $SRC" >&2
    exit 1
fi

echo "Uploading $(find "$SRC" -type f | wc -l) files"
echo "  from: $SRC"
echo "  to:   $REMOTE:$BUCKET/character_images/"
echo

rclone copy "$SRC" "$REMOTE:$BUCKET/character_images/" \
    --progress \
    --transfers 16 \
    --checkers 32 \
    --s3-no-check-bucket \
    --header-upload "Cache-Control: public, max-age=31536000, immutable"

echo
echo "Done. Verify one object is publicly readable through the bucket's custom"
echo "domain before rebuilding the frontend against it:"
echo "  curl -I https://<IMAGE_DOMAIN>/character_images/Zero_Two.png"
