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
import re

from flask import Blueprint, jsonify, request
from PIL import Image

import accent_extract
import db
import identity
import logs
import tempfiles
import thumbnails
from image_utils import validate_image_file
from imgchest_utils import ImgChestError, upload_to_imgchest
from ratelimit import rate_limited
from remote_images import MAX_FILE_SIZE, _allowed_portrait_url, imgchest_filename
from validation import (
    MAX_POOLS_LENGTH,
    MAX_RANK_LENGTH,
    MAX_SERIES_LENGTH,
    validate_character_name,
)

log = logs.get(__name__)
characters_bp = Blueprint("characters", __name__)


@characters_bp.route("/api/characters/<path:name>/view", methods=["POST"])
@rate_limited("view")
def record_view(name):
    """Note that the caller looked at this character.

    A POST rather than a side effect of loading the character, because a GET
    that quietly writes gets fired by prefetching, link previews and anything
    else that speculatively fetches -- none of which is a person looking at a
    page. The client asks explicitly, once, when the page is actually shown.

    Recording is best-effort: a failure here must never be what breaks a page
    the visitor is already looking at.
    """
    try:
        known = db.record_character_view(name, identity.current_identity().id)
    except Exception:
        log.exception("views.record_failed", character=name)
        return jsonify({"success": False}), 200
    return jsonify({"success": bool(known)}), (200 if known else 404)


@characters_bp.route("/upload", methods=["POST"])
@identity.require_signed_in
def upload():
    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]
    fn = file.filename
    if not fn:
        return jsonify({"error": "No file selected"}), 400

    log.info("upload.started", filename=fn)

    temp_path = tempfiles.reserve("upload", fn)
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
    """Add a new character.

    The portrait is either an uploaded file (uploaded to ImgChest) or, when the
    Add form already knows one from the catalog, an `image_url` on an accepted
    portrait host. A name that already exists is refused before either, so a
    duplicate never costs an ImgChest upload.
    """
    name = request.form.get("name", "").strip()
    provided_image_url = request.form.get("image_url", "").strip()
    if not name:
        json_data = request.get_json(silent=True)
        if json_data:
            name = str(json_data.get("name", "")).strip()
            series = str(json_data.get("series", "")).strip()
            rank = str(json_data.get("rank", "")).strip()
            provided_image_url = str(json_data.get("image_url", "")).strip()
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

    if db.get_characters() is None:
        return jsonify(
            {
                "error": "Characters not migrated to DB yet. Run scripts/migrate_v1_to_sqlite.py or scripts/import_mudae_catalog.py first."
            }
        ), 500

    # Refuse a duplicate up front: matching is on the folded name key, so a
    # differently-cased spelling of a character already here is caught too.
    existing = db.find_character(name)
    if existing and existing["in_library"]:
        return jsonify({"error": f'Character "{existing["name"]}" already exists'}), 400

    # A cookie-only visitor may add a character the catalog already knows; making
    # a brand-new entry needs a linked Discord account (DECISIONS.md §4). The
    # catalog add route is the "from the library" path and stays open.
    if existing is None and not identity.current_identity().is_signed_in:
        return (
            jsonify(
                {
                    "error": "Sign in with Discord to add a new character",
                    "code": "discord_required",
                }
            ),
            403,
        )

    image_url = ""
    if provided_image_url:
        if not _allowed_portrait_url(provided_image_url):
            return jsonify({"error": "Image must be from ImgChest or Mudae"}), 400
        image_url = provided_image_url

    if "image" in request.files:
        file = request.files["image"]
        fn = file.filename
        if fn:
            # Uploading a portrait is adding an image, so it needs an account --
            # the catalog URL path above does not upload and stays open.
            if not identity.current_identity().is_signed_in:
                return (
                    jsonify(
                        {
                            "error": "Sign in with Discord to add images",
                            "code": "discord_required",
                        }
                    ),
                    403,
                )
            temp_path = tempfiles.reserve("add", fn)
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

    # Gender and roulette are optional: an older client sends neither, and an
    # absent field has to leave the stored trait alone rather than read as a
    # cleared one.
    is_female = data.get("is_female")
    is_male = data.get("is_male")
    pools = data.get("pools")
    if is_female is not None and not isinstance(is_female, bool):
        return jsonify({"error": "is_female must be a boolean"}), 400
    if is_male is not None and not isinstance(is_male, bool):
        return jsonify({"error": "is_male must be a boolean"}), 400
    if pools is not None:
        if not isinstance(pools, str):
            return jsonify({"error": "pools must be a string"}), 400
        pools = pools.strip()
        if len(pools) > MAX_POOLS_LENGTH:
            return jsonify({"error": f"Pools too long (max {MAX_POOLS_LENGTH} characters)"}), 400

    try:
        if db.get_characters() is None:
            return jsonify(
                {
                    "error": "Characters not migrated to DB yet. Run scripts/migrate_v1_to_sqlite.py or scripts/import_mudae_catalog.py first."
                }
            ), 500
        if not db.update_character(
            orig_name,
            new_name,
            series,
            rank,
            is_female=is_female,
            is_male=is_male,
            pools=pools,
        ):
            return jsonify({"error": "Character not found"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    # No rename cascade: images, bookmarks and the timestamp all hang off
    # characters.id, so update_character above is the entire rename. v1 needed
    # 30 lines here rewriting three separate documents, able to half-fail.

    db.update_last_modified(new_name)
    return jsonify({"success": True, "message": "Character updated", "new_name": new_name})


@characters_bp.route("/api/set-main-image", methods=["POST"])
@identity.require_signed_in
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

    temp_path = tempfiles.reserve("main", fn)
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
                    "error": "Character data not loaded. Run scripts/migrate_v1_to_sqlite.py or scripts/import_mudae_catalog.py first."
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


_ACCENT_SEED = re.compile(r"^#[0-9a-fA-F]{6}$")


@characters_bp.route("/api/accent-override", methods=["POST"])
@identity.require_moderator
@rate_limited("edit_character")
def accent_override():
    """Set, clear, or pixel-pick a character's accent colour. Staff only.

    The accent is one value on the character row that every visitor sees, so
    this is not a per-identity preference: it is a moderator/owner action. A
    request either names a `seed`, clears with `clear: true`, or names a point
    (`image_id` or `portrait: true`, plus `u`/`v` in 0..1) to sample a pixel.
    """
    me = identity.current_identity()

    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Character name is required"}), 400

    if data.get("clear"):
        if not db.clear_accent_override(name):
            return jsonify({"error": "Character not found"}), 404
        return jsonify({"success": True, "seed": None, "manual": False})

    seed = data.get("seed")
    if seed is None:
        try:
            u = float(data["u"])
            v = float(data["v"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "A point (u, v) is required"}), 400
        if not (0.0 <= u <= 1.0 and 0.0 <= v <= 1.0):
            return jsonify({"error": "Point is outside the image"}), 400
        image = _image_for_point(name, data)
        if image is None:
            return jsonify({"error": "Could not read that image"}), 502
        seed = accent_extract.hex_at_point(image, u, v)
    else:
        if not isinstance(seed, str) or not _ACCENT_SEED.match(seed):
            return jsonify({"error": "seed must be a #rrggbb colour"}), 400
        seed = seed.lower()

    if not db.set_accent_override(name, seed, me.id):
        return jsonify({"error": "Character not found"}), 404
    return jsonify({"success": True, "seed": seed, "manual": True})


def _image_for_point(name, data):
    """The full-resolution image a pick refers to, or None.

    A gallery pick names an `image_id`, which resolves to the cached thumbnail
    the grid is showing (materialised if it has never been viewed). A portrait
    pick uses the character's own main image. Either way the URL is looked up
    from the database by name/id, never supplied by the caller, so this can only
    ever be asked for an image already in the library.
    """
    image_id = data.get("image_id")
    if image_id is not None:
        try:
            image_id = int(image_id)
        except (TypeError, ValueError):
            return None
        path = thumbnails.cache_path(image_id)
        if not path.is_file():
            accent_extract._materialise_thumbnail(image_id)
        if not path.is_file():
            return None
        try:
            with Image.open(path) as img:
                img.load()
                return img.convert("RGB")
        except Exception:
            log.warning("characters.accent_pick_unreadable", image_id=image_id)
            return None

    portrait = db.get_character_portrait(name)
    if not portrait:
        return None
    raw = accent_extract.fetch_portrait_bytes(portrait[1])
    if raw is None:
        return None
    return accent_extract.open_image_bytes(raw)
