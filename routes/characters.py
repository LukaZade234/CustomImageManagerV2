"""Characters, and the list of ones a visitor has saved.

A character is the thing custom images hang off: a name, a series, a rank and
one main portrait. These routes create them, edit them, and set that portrait —
either from an uploaded file or from a URL already on ImgChest.

Saving a character is per-visitor and carries no weight beyond a bookmark: it
is keyed to the cookie identity, and losing the cookie loses the list unless
the visitor has signed in with Discord.
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request

import db
import logs
from image_utils import validate_image_file
from imgchest_utils import ImgChestError, upload_to_imgchest
from ratelimit import rate_limited
from remote_images import MAX_FILE_SIZE, _safe_stored_filename, imgchest_filename
from validation import MAX_RANK_LENGTH, MAX_SERIES_LENGTH, validate_character_name

log = logs.get(__name__)
characters_bp = Blueprint("characters", __name__)


@characters_bp.route("/characters")
@characters_bp.route("/api/characters")
def get_characters():
    try:
        chars = db.get_characters()
        if chars is not None:
            return jsonify(chars)
        return jsonify(
            {
                "error": "Character data not loaded. Run scripts/import_characters_to_db.py with your CSV/mapping backup."
            }
        ), 503
    except Exception as e:
        log.exception("characters.list_failed")
        return jsonify({"error": str(e)}), 500


@characters_bp.route("/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    fn = file.filename
    if not fn:
        return jsonify({"error": "No file selected"}), 400

    log.info("upload.started", filename=fn)

    # Save temporarily (sanitized basename — no path traversal)
    safe_fn = _safe_stored_filename(fn)
    temp_path = os.path.join(".", "temp_upload_" + safe_fn)
    file.save(temp_path)
    file_size = os.path.getsize(temp_path)
    file_size_mb = file_size / (1024 * 1024)
    log.debug("upload.received", filename=fn, size_mb=round(file_size_mb, 2))

    if file_size > MAX_FILE_SIZE:
        log.warning(
            "upload.rejected",
            filename=fn,
            reason="too_large",
            size_mb=round(file_size_mb, 2),
            limit_mb=MAX_FILE_SIZE // (1024 * 1024),
        )
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify(
            {
                "error": f"File is {file_size_mb:.2f} MB; maximum allowed is {MAX_FILE_SIZE / (1024 * 1024):.0f} MB."
            }
        ), 400

    ok, err = validate_image_file(temp_path)
    if not ok:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": err}), 400

    log.debug("upload.sending", filename=fn)
    try:
        result = upload_to_imgchest(temp_path)
        if result:
            post_link, direct_link = result
            log.info("upload.succeeded", filename=file.filename)
            return jsonify({"success": True, "post_link": post_link, "direct_link": direct_link})
        else:
            log.warning("upload.failed", filename=file.filename, reason="imgchest_no_result")
            return jsonify(
                {"error": "Image host did not return a link (unexpected). Try again."}
            ), 500
    except ImgChestError as e:
        log.warning("upload.failed", filename=file.filename, reason="imgchest_error", error=str(e))
        return jsonify({"error": str(e)}), 503
    finally:
        # Clean up temp file
        if os.path.exists(temp_path):
            os.remove(temp_path)


@characters_bp.route("/api/saved", methods=["GET"])
def get_saved():
    try:
        return jsonify(db.get_saved_characters())
    except Exception:
        log.exception("saved.list_failed")
    return jsonify([])


@characters_bp.route("/api/saved", methods=["POST"])
def save_character():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Invalid character data"}), 400

    char_name = data["name"]
    ok, err = validate_character_name(char_name)
    if not ok:
        return jsonify({"error": err}), 400
    try:
        if not db.save_character(char_name):
            return jsonify({"error": "Character already saved"}), 400
        db.update_last_modified(char_name)
        return jsonify({"success": True, "message": "Character saved"})
    except Exception:
        log.exception("saved.add_failed")
        return jsonify({"error": "Failed to save character"}), 500


@characters_bp.route("/api/add-character", methods=["POST"])
@rate_limited("add_character")
def add_character():
    """Add a new character."""
    name = request.form.get("name", "").strip()
    if not name:
        json_data = request.get_json(silent=True)
        if json_data:
            name = str(json_data.get("name", "")).strip()
            series = str(json_data.get("series", "")).strip()
            rank = str(json_data.get("rank", "")).strip()
        else:
            return jsonify({"error": "Name is required"}), 400
    else:
        series = request.form.get("series", "").strip()
        rank = request.form.get("rank", "").strip()

    ok, err = validate_character_name(name)
    if not ok:
        return jsonify({"error": err}), 400
    if len(series) > MAX_SERIES_LENGTH:
        return jsonify({"error": f"Series too long (max {MAX_SERIES_LENGTH} characters)"}), 400
    if len(rank) > MAX_RANK_LENGTH:
        return jsonify({"error": f"Rank too long (max {MAX_RANK_LENGTH} characters)"}), 400

    image_url = ""

    if "image" in request.files:
        file = request.files["image"]
        fn = file.filename
        if fn:
            safe_fn = _safe_stored_filename(fn)
            temp_path = os.path.join(".", "temp_add_" + safe_fn)
            file.save(temp_path)
            try:
                result = upload_to_imgchest(
                    temp_path, upload_name=imgchest_filename(name, kind="main")
                )
                if result:
                    _, image_url = result
            except ImgChestError as e:
                log.warning("characters.main_image_failed", character=name, error=str(e))
                return jsonify({"error": str(e)}), 503
            except Exception:
                # Deliberately swallowed: the character is still created, just
                # without a portrait. Logged loudly because it is invisible to
                # the caller, who gets a success response either way.
                log.exception("characters.main_image_failed", character=name)
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    try:
        if db.get_characters() is None:
            return jsonify(
                {
                    "error": "Characters not migrated to DB yet. Run scripts/import_characters_to_db.py first."
                }
            ), 500
        if not db.add_character(name, series, rank, image_url):
            return jsonify({"error": f'Character "{name}" already exists'}), 400
        db.update_last_modified(name)
        return jsonify({"success": True, "message": f'Added "{name}"'})
    except Exception as e:
        log.exception("characters.add_failed")
        return jsonify({"error": str(e)}), 500


@characters_bp.route("/api/saved/<path:name>", methods=["DELETE"])
def remove_saved(name):
    try:
        if not db.unsave_character(name):
            return jsonify({"error": "Character not found in saved list"}), 404
        return jsonify({"success": True, "message": "Character removed"})
    except Exception:
        log.exception("saved.remove_failed")
        return jsonify({"error": "Failed to remove character"}), 500


@characters_bp.route("/api/edit-character", methods=["POST"])
@rate_limited("edit_character")
def edit_character():
    data = request.get_json()
    required = ["original_name", "new_name", "series", "rank"]
    if not data or not all(k in data for k in required):
        return jsonify({"error": "Missing required fields"}), 400

    orig_name = data["original_name"]
    new_name = data["new_name"].strip()
    series = data["series"].strip()
    rank = data["rank"].strip()

    if not new_name:
        return jsonify({"error": "Name cannot be empty"}), 400

    ok, err = validate_character_name(new_name)
    if not ok:
        return jsonify({"error": err}), 400
    if len(series) > MAX_SERIES_LENGTH:
        return jsonify({"error": f"Series too long (max {MAX_SERIES_LENGTH} characters)"}), 400
    if len(rank) > MAX_RANK_LENGTH:
        return jsonify({"error": f"Rank too long (max {MAX_RANK_LENGTH} characters)"}), 400

    try:
        if db.get_characters() is None:
            return jsonify(
                {
                    "error": "Characters not migrated to DB yet. Run scripts/import_characters_to_db.py first."
                }
            ), 500
        if not db.update_character(orig_name, new_name, series, rank):
            return jsonify({"error": "Character not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # No rename cascade: images, bookmarks and the timestamp all hang off
    # characters.id, so update_character above is the entire rename. v1 needed
    # 30 lines here rewriting three separate documents, able to half-fail.

    db.update_last_modified(new_name)
    return jsonify({"success": True, "message": "Character updated", "new_name": new_name})


@characters_bp.route("/api/set-main-image", methods=["POST"])
@rate_limited("edit_character")
def set_main_image():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400
    if "character_name" not in request.form:
        return jsonify({"error": "Character name is required"}), 400

    file = request.files["file"]
    char_name = request.form["character_name"].strip()

    ok, err = validate_character_name(char_name)
    if not ok:
        return jsonify({"error": err}), 400

    fn = file.filename
    if not fn:
        return jsonify({"error": "No file selected"}), 400

    safe_fn = _safe_stored_filename(fn)
    temp_path = os.path.join(".", "temp_main_" + safe_fn)
    file.save(temp_path)

    main_size = os.path.getsize(temp_path)
    if main_size > MAX_FILE_SIZE:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        main_mb = main_size / (1024 * 1024)
        return jsonify(
            {
                "error": f"File is {main_mb:.2f} MB; maximum allowed is {MAX_FILE_SIZE / (1024 * 1024):.0f} MB."
            }
        ), 400

    ok, val_err = validate_image_file(temp_path)
    if not ok:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return jsonify({"error": val_err}), 400

    try:
        result = upload_to_imgchest(
            temp_path, upload_name=imgchest_filename(char_name, kind="main")
        )
        if not result:
            return jsonify({"error": "Failed to upload to ImgChest"}), 500

        post_link, direct_link = result

        if db.get_characters() is None:
            return jsonify(
                {
                    "error": "Character data not loaded. Run scripts/import_characters_to_db.py first."
                }
            ), 503
        if db.set_main_image(char_name, direct_link):
            db.update_last_modified(char_name)
            return jsonify(
                {"success": True, "message": "Main image updated", "image_url": direct_link}
            )
        return jsonify({"error": "Character not found"}), 404
    except ImgChestError as e:
        log.warning("characters.main_image_failed", reason="imgchest_error", error=str(e))
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        log.exception("characters.main_image_failed")
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
