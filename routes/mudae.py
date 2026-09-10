"""Mudae routes.

The Discord self-bot is a metadata fetcher, not part of the data layer: it looks
a character up in Mudae's own database so a person does not have to retype the
name, series and rank, and grabs the card art. Everything it returns goes
through the same validation and the same ImgChest upload as a manual entry.

Each call spends one of Discord's ~1000 daily interactions, which is why these
are rate limited more tightly than anything else, and why `add-series` reports
progress rather than silently running for minutes.
"""

from __future__ import annotations

import json
import os
import queue
import threading

import requests
from flask import Blueprint, Response, jsonify, request

import db
import logs
import mudae_discord
from image_utils import validate_image_file
from imgchest_utils import ImgChestError, upload_to_imgchest
from mudae_discord import MudaeAmbiguousSeries, MudaeCancelled, MudaeError
from ratelimit import rate_limited
from remote_images import (
    MAX_FILE_SIZE,
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


def _persist_mudae_character(info, *, overwrite_main=False):
    """
    Add character from CharacterInfo, or update main image if already exists and overwrite_main.
    Returns (action, image_url) where action is 'added' | 'exists' | 'updated'.
    """
    if db.get_characters() is None:
        raise RuntimeError(
            "Characters not migrated to DB yet. Run scripts/import_characters_to_db.py first."
        )

    name = (info.name or "").strip()
    ok, err = validate_character_name(name)
    if not ok:
        raise ValueError(err)

    series = (info.series or "").strip()[:MAX_SERIES_LENGTH]
    rank = (info.rank or "").strip()[:MAX_RANK_LENGTH]
    image_url = ""
    if info.image_url:
        image_url = _upload_remote_image_to_imgchest(info.image_url, name)

    existing = [c for c in (db.get_characters() or []) if c.get("name") == name]
    if existing:
        if overwrite_main and image_url:
            if not db.set_main_image(name, image_url):
                raise RuntimeError("Failed to update main image")
            db.update_last_modified(name)
            return "updated", image_url
        return "exists", existing[0].get("image") or image_url

    if not db.add_character(name, series, rank, image_url):
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


@mudae_bp.route("/api/mudae/lookup-series", methods=["POST"])
@rate_limited("mudae")
def mudae_lookup_series():
    """
    Resolve a series name via Mudae $ima.
    Body: { series }
    Returns { type: 'series', series_label } or { type: 'candidates', candidate_matches }.
    """
    data = request.get_json(silent=True) or {}
    series = str(data.get("series") or "").strip()
    if not series:
        return jsonify({"error": "Series is required"}), 400
    if len(series) > MAX_SERIES_LENGTH:
        return jsonify({"error": f"Series too long (max {MAX_SERIES_LENGTH} characters)"}), 400

    try:
        result = mudae_discord.lookup_series(series)
        return jsonify(result.to_dict())
    except MudaeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception:
        log.exception("mudae.lookup_series_failed")
        return jsonify(
            {"error": "Something went wrong during Mudae series lookup. Try again in a moment."}
        ), 500


@mudae_bp.route("/api/mudae/add-series", methods=["POST"])
@rate_limited("mudae")
def mudae_add_series():
    """
    Bulk-add characters from a series via $ima then $im each.
    Body: { series }
    Query ?stream=1 for Server-Sent Events with live progress.
    """
    data = request.get_json(silent=True) or {}
    series = str(data.get("series") or "").strip()
    if not series:
        return jsonify({"error": "Series is required"}), 400
    if len(series) > MAX_SERIES_LENGTH:
        return jsonify({"error": f"Series too long (max {MAX_SERIES_LENGTH} characters)"}), 400
    stream = request.args.get("stream") == "1"

    try:
        if db.get_characters() is None:
            return jsonify(
                {
                    "error": "Characters not migrated to DB yet. Run scripts/import_characters_to_db.py first."
                }
            ), 500

        existing = {
            c.get("name", "").casefold() for c in (db.get_characters() or []) if c.get("name")
        }
        mudae_discord.clear_series_cancel()

        if stream:
            progress_q: queue.Queue = queue.Queue()

            def _worker():
                try:
                    payload = _run_mudae_add_series(series, existing, progress_q.put)
                    progress_q.put(("done", payload))
                except MudaeAmbiguousSeries as e:
                    progress_q.put(("error", e.to_dict()))
                except Exception as e:
                    progress_q.put(("error", {"error": str(e)}))

            def _sse_stream():
                thread = threading.Thread(target=_worker, daemon=True)
                thread.start()
                while True:
                    item = progress_q.get()
                    kind = item[0]
                    if kind == "progress":
                        _, event, event_data = item
                        yield f"event: {event}\ndata: {json.dumps(event_data)}\n\n"
                    elif kind == "done":
                        yield f"event: done\ndata: {json.dumps(item[1])}\n\n"
                        break
                    elif kind == "error":
                        yield f"event: error\ndata: {json.dumps(item[1])}\n\n"
                        break
                thread.join(timeout=1.0)

            return Response(
                _sse_stream(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

        return jsonify(_run_mudae_add_series(series, existing))
    except MudaeAmbiguousSeries as e:
        return jsonify(e.to_dict()), 409
    except MudaeCancelled as e:
        return jsonify({"error": str(e), "cancelled": True}), 499
    except MudaeError as e:
        return jsonify({"error": str(e)}), 503
    except ImgChestError as e:
        return jsonify({"error": str(e)}), 503
    except Exception:
        log.exception("mudae.add_series_failed")
        return jsonify(
            {"error": "Something went wrong during series import. Try again in a moment."}
        ), 500


@mudae_bp.route("/api/mudae/cancel-series", methods=["POST"])
def mudae_cancel_series():
    """Request stop of an in-progress bulk series import (checked between characters)."""
    mudae_discord.request_series_cancel()
    return jsonify({"success": True, "message": "Cancel requested"})


def _run_mudae_add_series(series, existing, progress_cb=None):
    """Run bulk series import. progress_cb(event, payload) for SSE when set."""
    added_out = []
    persist_errors = []

    def _emit(event, payload):
        if progress_cb:
            progress_cb(("progress", event, payload))

    def on_character(info):
        try:
            action, image_url = _persist_mudae_character(info)
            if action == "added":
                entry = {
                    **info.to_dict(),
                    "image_url": image_url or info.image_url,
                }
                added_out.append(entry)
                _emit("added", entry)
            elif action == "exists":
                persist_errors.append({"name": info.name, "error": "already exists", "_skip": True})
                _emit("skipped", {"name": info.name, "reason": "already exists"})
        except MudaeCancelled:
            raise
        except Exception as e:
            log.exception("mudae.persist_failed", character=getattr(info, "name", None))
            persist_errors.append(
                {
                    "name": getattr(info, "name", "?"),
                    "error": "Could not save character",
                }
            )
            raise MudaeError("Could not save character") from e

    try:
        result = mudae_discord.list_series_and_lookup(
            series,
            on_character=on_character,
            skip_names=existing,
            on_progress=_emit,
        )
    except MudaeCancelled:
        result = {
            "series": series,
            "total_listed": 0,
            "added": [],
            "skipped": [],
            "failed": [],
            "cancelled": True,
        }

    skipped = list(result.get("skipped") or [])
    failed = list(result.get("failed") or [])
    for pe in persist_errors:
        if pe.pop("_skip", False):
            skipped.append(pe["name"])
        else:
            failed.append(pe)

    series_name = mudae_discord.clean_series_label(result.get("series") or series)
    total = int(result.get("total_listed") or 0)
    processed = len(added_out) + len(skipped) + len(failed)
    cancelled = bool(result.get("cancelled"))

    if cancelled:
        message = (
            f'Series "{series_name}" import cancelled — {processed}/{total} processed — '
            f"added {len(added_out)}, skipped {len(skipped)}, failed {len(failed)}"
        )
    else:
        message = (
            f'Series "{series_name}": {processed}/{total} — '
            f"added {len(added_out)}, skipped {len(skipped)}, failed {len(failed)}"
        )

    return {
        "success": True,
        "series": series_name,
        "total_listed": total,
        "processed": processed,
        "added": added_out,
        "skipped": skipped,
        "failed": failed,
        "cancelled": cancelled,
        "message": message,
    }


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
                    "error": "Character data not loaded. Run scripts/import_characters_to_db.py first."
                }
            ), 503

        chars = db.get_characters() or []
        if not any(c.get("name") == char_name for c in chars):
            return jsonify({"error": "Character not found"}), 404

        info = mudae_discord.lookup_character_exact(char_name)
        if not info.image_url:
            return jsonify({"error": "Mudae reply had no image"}), 502

        image_url = _upload_remote_image_to_imgchest(info.image_url, char_name)
        if not db.set_main_image(char_name, image_url):
            return jsonify({"error": "Character not found"}), 404
        db.update_last_modified(char_name)

        return jsonify(
            {
                "success": True,
                "message": "Main image updated from Mudae",
                "image_url": image_url,
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
