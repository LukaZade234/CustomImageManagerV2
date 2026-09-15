"""Mudae routes.

The Discord self-bot is a metadata fetcher, not part of the data layer: it looks
a character up in Mudae's own database so a person does not have to retype the
name, series and rank, and grabs the card art. Everything it returns goes
through the same validation as a manual entry.

A series is fetched in one shot: `$imartsmi- <series>` makes Mudae DM the whole
roster with ranks and portraits, which replaces an `$ima` plus one `$im` per
character. Each Mudae call spends one of Discord's ~1000 daily interactions,
which is why these are rate limited more tightly than anything else.
"""

from __future__ import annotations

import os

import requests
from flask import Blueprint, Response, jsonify, request

import catalog_import
import db
import logs
import mudae_discord
import portrait_mirror
from image_utils import validate_image_file
from imgchest_utils import ImgChestError, upload_to_imgchest
from mudae_discord import MudaeError
from ratelimit import rate_limited
from remote_images import (
    MAX_FILE_SIZE,
    _allowed_portrait_url,
    _fetch_image_from_url_for_import,
    _get_with_validated_redirects,
    _safe_import_image_url,
    imgchest_filename,
)
from validation import MAX_RANK_LENGTH, MAX_SERIES_LENGTH, validate_character_name

log = logs.get(__name__)
mudae_bp = Blueprint("mudae", __name__)


def _upload_remote_image_to_imgchest(image_url, character_name):
    """Download a remote image URL and upload to ImgChest. Returns direct_link.

    `character_name` only names the file on ImgChest, but it has to be passed in
    rather than inferred: this is called both while adding a character that does
    not exist yet and while refreshing an existing one's portrait.
    """
    if not image_url:
        raise ValueError("No image URL from Mudae")
    temp_path, _ = _fetch_image_from_url_for_import(image_url)
    try:
        ok, val_err = validate_image_file(temp_path)
        if not ok:
            raise ValueError(val_err or "Invalid image from Mudae")
        result = upload_to_imgchest(
            temp_path, upload_name=imgchest_filename(character_name, kind="main-mudae")
        )
        if not result:
            raise ImgChestError("Failed to upload Mudae image to ImgChest")
        _, direct_link = result
        return direct_link
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _mudae_main_image_url(image_url, character_name):
    """The URL to store as a character's main image, given one from Mudae.

    Mudae's own portrait hosts (`mudae.net`) are hotlinkable and are what the
    catalog and the bulk extract store, so such a URL is kept as it came back.
    A host we cannot rely on -- notably a Discord CDN link that expires -- is
    downloaded and re-hosted on ImgChest instead.
    """
    if not image_url:
        return ""
    if _allowed_portrait_url(image_url):
        return image_url
    return _upload_remote_image_to_imgchest(image_url, character_name)


def _read_image_bytes(image_url):
    """Raw bytes of a remote image, fetched through the import SSRF guards."""
    temp_path, _ = _fetch_image_from_url_for_import(image_url)
    try:
        with open(temp_path, "rb") as handle:
            return handle.read()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def _refresh_main_portrait(char_name, info):
    """Set a character's main image from a live `$im` card, mirroring it to R2.

    The fresh portrait is written to the catalog and mirrored under the same
    content-hashed key the batch script uses, so the page serves it from the CDN
    rather than ImgChest. When the mirror cannot run (rclone or its config absent
    in this runtime), it falls back to the previous behaviour -- store the Mudae
    URL, or re-host on ImgChest for a non-durable host -- and leaves the catalog
    row needing a mirror for the next batch run, so the refresh never fails over
    the CDN. Returns (stored_url, mirror_key) or None if the row vanished.
    """
    image_url = info.image_url
    catalog = db.refresh_catalog_portrait(info.name or char_name, info.series, info.rank, image_url)
    if catalog:
        catalog_id, name_key = catalog
        raw = _read_image_bytes(image_url)
        key = portrait_mirror.mirror(catalog_id, raw) if raw else None
        if key:
            db.record_catalog_portrait_mirrors([(name_key, key)])
            if db.set_main_image(char_name, image_url):
                return image_url, key
    if db.set_main_image(char_name, _mudae_main_image_url(image_url, char_name)):
        return image_url, None
    return None


def _persist_mudae_character(info, *, overwrite_main=False):
    """
    Add character from CharacterInfo, or update main image if already exists and overwrite_main.
    Returns (action, image_url) where action is 'added' | 'exists' | 'updated'.
    """
    if db.get_characters() is None:
        raise RuntimeError(
            "Characters not migrated to DB yet. Run scripts/migrate_v1_to_sqlite.py or scripts/import_mudae_catalog.py first."
        )

    name = (info.name or "").strip()
    ok, err = validate_character_name(name)
    if not ok:
        raise ValueError(err)

    series = (info.series or "").strip()[:MAX_SERIES_LENGTH]
    rank = (info.rank or "").strip()[:MAX_RANK_LENGTH]
    image_url = _mudae_main_image_url(info.image_url, name)

    existing = [c for c in (db.get_characters() or []) if c.get("name") == name]
    if existing:
        if overwrite_main and image_url:
            if not db.set_main_image(name, image_url):
                raise RuntimeError("Failed to update main image")
            db.set_character_traits(
                name, is_female=info.is_female, is_male=info.is_male, pools=info.pools
            )
            return "updated", image_url
        return "exists", existing[0].get("image") or image_url

    if not db.add_character(
        name,
        series,
        rank,
        image_url,
        is_female=info.is_female,
        is_male=info.is_male,
        pools=info.pools,
    ):
        raise RuntimeError(f'Failed to add "{name}"')
    db.update_last_modified(name)
    return "added", image_url


@mudae_bp.route("/api/mudae/status", methods=["GET"])
def mudae_status():
    return jsonify({"configured": mudae_discord.configured()})


@mudae_bp.route("/api/mudae/proxy-image", methods=["GET"])
def mudae_proxy_image():
    """
    Proxy a remote character image for browser preview (Discord CDN often blocks hotlinking).
    Only available when Mudae Discord env is configured; URL must pass SSRF checks.
    """
    if not mudae_discord.configured():
        return jsonify({"error": "Mudae is not configured"}), 503
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "Missing url"}), 400
    if url.startswith("//"):
        url = "https:" + url
    if not _safe_import_image_url(url):
        return jsonify({"error": "URL not allowed"}), 403
    try:
        r = _get_with_validated_redirects(url, timeout=60, allow_redirects=False)
        if r.status_code != 200:
            return jsonify({"error": f"Image server returned {r.status_code}"}), 502
        raw = r.content
        if len(raw) > MAX_FILE_SIZE + 2 * 1024 * 1024:
            return jsonify({"error": "Image too large"}), 413
        if not raw:
            return jsonify({"error": "Empty image"}), 502
        ct = r.headers.get("Content-Type") or "image/png"
        if "image/" not in ct and "octet-stream" not in ct:
            ct = "image/png"
        return Response(raw, mimetype=ct, headers={"Cache-Control": "private, max-age=300"})
    except ValueError as e:
        # A blocked redirect hop, not a transport failure.
        log.warning("mudae.proxy_refused", error=str(e))
        return jsonify({"error": "URL not allowed"}), 403
    except requests.RequestException:
        log.exception("mudae.proxy_failed")
        return jsonify({"error": "Could not load image"}), 502


@mudae_bp.route("/api/mudae/lookup-character", methods=["POST"])
@rate_limited("mudae")
def mudae_lookup_character():
    """
    Lookup a character via Mudae $im.
    Body: { name, add?: bool }
    When add is true and a single card is found, persists to DB (ImgChest + add_character).
    """
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    do_add = bool(data.get("add"))
    if not name:
        return jsonify({"error": "Name is required"}), 400
    ok, err = validate_character_name(name)
    if not ok:
        return jsonify({"error": err}), 400

    try:
        result = mudae_discord.lookup_character(name)
        payload = result.to_dict()
        if result.type == "candidates":
            return jsonify(payload)

        info = result.character
        if do_add and info:
            action, image_url = _persist_mudae_character(info)
            payload["action"] = action
            payload["character"] = {
                **info.to_dict(),
                "image_url": image_url or info.image_url,
                "mudae_image_url": info.image_url,
            }
            if action == "exists":
                return jsonify({**payload, "error": f'Character "{info.name}" already exists'}), 400
            payload["success"] = True
            payload["message"] = f'Added "{info.name}"'
        return jsonify(payload)
    except MudaeError as e:
        return jsonify({"error": str(e)}), 503
    except ImgChestError as e:
        return jsonify({"error": str(e)}), 503
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        log.exception("mudae.lookup_failed")
        return jsonify(
            {"error": "Something went wrong during Mudae lookup. Try again in a moment."}
        ), 500


@mudae_bp.route("/api/mudae/series-extract", methods=["POST"])
@rate_limited("mudae")
def mudae_series_extract():
    """Fetch a whole series via one `$imartsmi-` DM and return it for review.

    Body: { series }
    Each character is marked `in_library`, with the fields that differ from the
    working row so the UI can show what applying would change.
    """
    data = request.get_json(silent=True) or {}
    series = str(data.get("series") or "").strip()
    if not series:
        return jsonify({"error": "Series is required"}), 400
    if len(series) > MAX_SERIES_LENGTH:
        return jsonify({"error": f"Series too long (max {MAX_SERIES_LENGTH} characters)"}), 400

    if db.get_characters() is None:
        return jsonify(
            {
                "error": "Characters not migrated to DB yet. Run scripts/migrate_v1_to_sqlite.py or scripts/import_mudae_catalog.py first."
            }
        ), 500

    try:
        raw = mudae_discord.fetch_series_extract(series)
    except MudaeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception:
        log.exception("mudae.series_extract_failed")
        return jsonify(
            {"error": "Something went wrong fetching the series. Try again in a moment."}
        ), 500

    parsed = catalog_import.parse_series_extract(raw)
    if not parsed.characters:
        return jsonify(
            {
                "error": (
                    "Mudae's reply had no characters. Check the series name, then try again."
                ),
                "issues": [
                    {"line": issue.line_no, "text": issue.text, "reason": issue.reason}
                    for issue in parsed.issues[:20]
                ],
            }
        ), 502

    series_label = parsed.series or series
    in_library = {
        catalog_import.name_key(c.get("name") or ""): c for c in (db.get_characters() or [])
    }

    items = []
    for character in parsed.characters:
        row = in_library.get(catalog_import.name_key(character.name))
        if row is None:
            items.append(
                {
                    "name": character.name,
                    "rank": character.rank,
                    "image_url": character.image_url,
                    "pool": character.pool,
                    "in_library": False,
                    "changes": ["create"],
                }
            )
            continue
        changes = []
        if series_label and row.get("series") != series_label:
            changes.append("series")
        if character.rank and row.get("rank") != character.rank:
            changes.append("rank")
        if character.image_url and row.get("image") != character.image_url:
            changes.append("image")
        items.append(
            {
                "name": row.get("name") or character.name,
                "rank": character.rank,
                "image_url": character.image_url,
                "pool": character.pool,
                "in_library": True,
                "changes": changes,
            }
        )

    return jsonify(
        {
            "series": series_label,
            "listed": parsed.listed,
            "total": parsed.total,
            "items": items,
            "new_count": sum(1 for item in items if not item["in_library"]),
            "update_count": sum(1 for item in items if item["in_library"] and item["changes"]),
            "unchanged_count": sum(
                1 for item in items if item["in_library"] and not item["changes"]
            ),
        }
    )


@mudae_bp.route("/api/mudae/series-extract/apply", methods=["POST"])
@rate_limited("add_character")
def mudae_series_extract_apply():
    """Create and refresh working characters from a reviewed series extract.

    Body: { series, items: [{name, rank, image_url}] }
    No Discord call: the extract was already fetched. Portraits are the Mudae
    URLs from the DM, so a changed one is written as-is, with no ImgChest upload.
    """
    data = request.get_json(silent=True) or {}
    series = str(data.get("series") or "").strip()[:MAX_SERIES_LENGTH]
    raw_items = data.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return jsonify({"error": "No characters to add"}), 400
    if len(raw_items) > 2000:
        return jsonify({"error": "Too many characters in one request"}), 400

    if db.get_characters() is None:
        return jsonify(
            {
                "error": "Characters not migrated to DB yet. Run scripts/migrate_v1_to_sqlite.py or scripts/import_mudae_catalog.py first."
            }
        ), 500

    items = []
    rejected = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        rank = str(raw.get("rank") or "").strip()[:MAX_RANK_LENGTH]
        image_url = str(raw.get("image_url") or "").strip()
        ok, err = catalog_import.validate_catalog_name(name)
        if not ok:
            rejected.append({"name": name, "error": err or "invalid name"})
            continue
        if image_url and not _allowed_portrait_url(image_url):
            rejected.append({"name": name, "error": "Image must be from ImgChest or Mudae"})
            continue
        items.append({"name": name, "rank": rank, "image": image_url})

    if not items:
        return jsonify({"error": "No valid characters to add", "rejected": rejected}), 400

    try:
        result = db.apply_series_characters(series, items)
    except Exception:
        log.exception("mudae.series_apply_failed")
        return jsonify({"error": "Failed to save the series. Try again in a moment."}), 500

    result["rejected"] = rejected
    message = (
        f'Series "{series}" — added {result["created"]}, '
        f"updated {result['updated']}, unchanged {result['unchanged']}"
    )
    return jsonify({"success": True, "series": series, "message": message, **result})


@mudae_bp.route("/api/mudae/refresh-main-image", methods=["POST"])
@rate_limited("mudae")
def mudae_refresh_main_image():
    """Fetch character card image from Mudae $im and set as main image."""
    data = request.get_json(silent=True) or {}
    char_name = str(data.get("character_name") or data.get("name") or "").strip()
    if not char_name:
        return jsonify({"error": "character_name is required"}), 400
    ok, err = validate_character_name(char_name)
    if not ok:
        return jsonify({"error": err}), 400

    try:
        if db.get_characters() is None:
            return jsonify(
                {
                    "error": "Character data not loaded. Run scripts/migrate_v1_to_sqlite.py or scripts/import_mudae_catalog.py first."
                }
            ), 503

        chars = db.get_characters() or []
        if not any(c.get("name") == char_name for c in chars):
            return jsonify({"error": "Character not found"}), 404

        info = mudae_discord.lookup_character_exact(char_name)
        if not info.image_url:
            return jsonify({"error": "Mudae reply had no image"}), 502

        result = _refresh_main_portrait(char_name, info)
        if result is None:
            return jsonify({"error": "Character not found"}), 404
        image_url, mirror_key = result
        # The same card carries the gender and pools, so refresh those too.
        db.set_character_traits(
            char_name,
            is_female=info.is_female,
            is_male=info.is_male,
            pools=info.pools,
        )

        return jsonify(
            {
                "success": True,
                "message": "Main image updated from Mudae",
                "image_url": image_url,
                "image_thumb": mirror_key or "",
                "character": info.to_dict(),
            }
        )
    except MudaeError as e:
        return jsonify({"error": str(e)}), 503
    except ImgChestError as e:
        return jsonify({"error": str(e)}), 503
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception:
        log.exception("mudae.refresh_main_failed")
        return jsonify(
            {"error": "Something went wrong updating the main image. Try again in a moment."}
        ), 500
