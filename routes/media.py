"""Serving image bytes.

Two different things, both of which end up as an <img> src:

- `/thumbs/<id>.webp` renders a small WebP of an ImgChest image on first
  request, caches it on disk and mirrors it to R2. The images themselves must
  stay PNGs on ImgChest because Mudae's $ai command accepts nothing else, but
  nothing requires a browser to download a 1.9 MB PNG to draw a 220px row. Once
  mirrored, the row's key is what listings hand the client, so the grid loads the
  thumbnail from the CDN rather than through here.
- `/api/download-image-proxy` fetches a remote image on the caller's behalf, so
  it goes through the same SSRF guards as any other URL a visitor supplies.

Keyed by row id rather than by URL throughout: the endpoints can only ever be
asked for images already in the database, so there is no way to hand one an
arbitrary URL to fetch.
"""

from __future__ import annotations

import requests
from flask import Blueprint, Response, abort, jsonify, redirect, request, send_from_directory

import db
import logs
import thumbnails
from remote_images import (
    MAX_FILE_SIZE,
    _allowed_image_proxy_url,
    _get_with_validated_redirects,
)

log = logs.get(__name__)
media_bp = Blueprint("media", __name__)


@media_bp.route("/thumbs/<int:image_id>.webp", methods=["GET"])
def serve_thumbnail(image_id):
    """A small WebP of one image, generated on first request, cached and mirrored.

    Keyed by row id, so this can only be asked for images already in the
    database; there is no way to hand it a URL of your choosing.

    Any failure redirects to the original on ImgChest rather than erroring. A
    thumbnail is an optimisation, and a missing one should cost bandwidth, not a
    broken image. A failed *mirror* is not a failure at all: the local cache still
    serves, and the backfill or the next generation fills the mirror in.
    """
    path = thumbnails.cache_path(image_id)
    if path.is_file():
        return _thumbnail_response(path)

    source = db.get_image_url(image_id)
    if not source:
        abort(404)
    if not thumbnails.is_thumbnailable(source):
        return redirect(source)

    try:
        response = _get_with_validated_redirects(source, timeout=30, allow_redirects=False)
        if response.status_code != 200:
            raise ValueError(f"source returned {response.status_code}")
        data = thumbnails.render(response.content)
        thumbnails.store(image_id, data)
    except Exception as e:
        log.warning("thumbnail.failed", image_id=image_id, error=f"{type(e).__name__}: {e}")
        return redirect(source)

    # Mirror it to R2, so the grid can load it from the CDN instead of through
    # the origin and the file stops being origin-only. Best effort: rclone is
    # absent in a dev checkout, in which case the local cache still serves and the
    # backfill fills the mirror in later. Recording the key is what promotes the
    # client to the CDN on its next listing, so a failure here only costs that.
    key = thumbnails.mirror(image_id, data)
    if key:
        try:
            db.set_thumb_key(image_id, key)
        except Exception as e:
            log.warning(
                "thumbnail.mirror_record_failed",
                image_id=image_id,
                error=f"{type(e).__name__}: {e}",
            )

    return _thumbnail_response(path)


def _thumbnail_response(path):
    response = send_from_directory(path.parent.resolve(), path.name, mimetype="image/webp")
    # Derived from an immutable source keyed by a row id that never changes its
    # URL, so this can be cached hard. Cloudflare then serves it from the edge
    # and the origin sees each thumbnail once, globally.
    response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    return response


@media_bp.route("/api/download-image-proxy", methods=["POST"])
def download_image_proxy():
    """
    Fetch a remote image server-side so the browser can save it (avoids CORS on ImgChest URLs).
    """
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Missing url"}), 400
    if url.startswith("//"):
        url = "https:" + url
    if not _allowed_image_proxy_url(url):
        return jsonify({"error": "Only ImgChest image URLs can be proxied for download"}), 403
    try:
        r = requests.get(
            url,
            timeout=90,
            headers={"User-Agent": "ImgManager/1.0"},
        )
        if r.status_code != 200:
            return jsonify({"error": f"Image server returned {r.status_code}"}), 502
        raw = r.content
        if len(raw) > MAX_FILE_SIZE + 2 * 1024 * 1024:
            return jsonify({"error": "Image too large"}), 413
        ct = r.headers.get("Content-Type") or "application/octet-stream"
        if "image/" not in ct and "octet-stream" not in ct:
            ct = "application/octet-stream"
        return Response(raw, mimetype=ct)
    except requests.RequestException as e:
        return jsonify({"error": str(e)}), 502
