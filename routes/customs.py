"""Custom images: adding them, ordering them, and moderating them.

The heart of the app. A custom image is one a visitor added to a character, as
opposed to the default portrait, and every route here operates on a set of them.

Moderation is built on one property of the storage: nothing ever deletes from
ImgChest, so a "removed" image is still live at its URL forever. That makes
remove and restore symmetric and cheap, and it is why removal is soft and
scoped to the owner, hiding is per-viewer, and reporting needs two distinct
reporters before anything happens to someone else's image.
"""

from __future__ import annotations

import os

from flask import Blueprint, jsonify, request

import db
import identity
import logs
from image_utils import (
    detect_format,
    is_animated,
    prepare_for_upload,
    read_image_dimensions,
    validate_image_file,
)
from imgchest_utils import ImgChestError, upload_to_imgchest
from ratelimit import rate_limited
from remote_images import (
    MAX_FILE_SIZE,
    MAX_IMPORT_URLS,
    _dedupe_import_urls_preserve_order,
    _fetch_image_from_url_for_import,
    _safe_stored_filename,
    imgchest_filename,
)
from validation import validate_character_name

log = logs.get(__name__)
customs_bp = Blueprint("customs", __name__)


def _run_single_custom_upload_from_temp(temp_path, display_filename, upload_name=None):
    """
    Validate, convert, upload one temp file to ImgChest.
    Returns (direct_link, None) on success, or (None, error_message).
    Removes temp files when done.
    """
    conversion_created_new_file = False
    final_path = temp_path
    try:
        file_size = os.path.getsize(temp_path)
        file_size_mb = file_size / (1024 * 1024)
        log.debug("upload.received", filename=display_filename, size_mb=round(file_size_mb, 2))

        if file_size > MAX_FILE_SIZE:
            log.warning(
                "upload.rejected",
                filename=display_filename,
                reason="too_large",
                size_mb=round(file_size_mb, 2),
            )
            if os.path.exists(temp_path):
                os.remove(temp_path)
            limit_mb = MAX_FILE_SIZE / (1024 * 1024)
            return (
                None,
                f"{display_filename}: File is {file_size_mb:.2f} MB; maximum allowed is {limit_mb:.0f} MB.",
                None,
            )

        ok, val_err = validate_image_file(temp_path)
        if not ok:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return None, f"{display_filename}: {val_err}", None

        # Animated GIFs pass through: re-encoding them costs the animation, which
        # is usually the reason the image was chosen. Everything else is
        # normalised, decided by the file's own bytes rather than its name.
        if detect_format(temp_path) == "GIF" and is_animated(temp_path):
            log.debug("upload.kept_as_is", filename=display_filename, reason="animated_gif")
        else:
            prepared_path, convert_error = prepare_for_upload(temp_path)
            if prepared_path:
                conversion_created_new_file = prepared_path != temp_path
                final_path = prepared_path
                log.debug("upload.prepared", filename=display_filename)
            else:
                err_msg = f"{display_filename}: {convert_error or 'Could not process image'}"
                log.warning(
                    "upload.rejected", filename=display_filename, reason="preparation_failed"
                )
                if os.path.exists(temp_path):
                    os.remove(temp_path)
                return None, err_msg, None

        final_size = os.path.getsize(final_path)
        if final_size > MAX_FILE_SIZE:
            final_mb = final_size / (1024 * 1024)
            limit_mb = MAX_FILE_SIZE / (1024 * 1024)
            log.warning(
                "upload.rejected",
                filename=display_filename,
                reason="too_large_after_processing",
                bytes=final_size,
            )
            return (
                None,
                f"{display_filename}: After processing the file is {final_mb:.2f} MB, which exceeds "
                f"ImgChest's limit of {limit_mb:.0f} MB.",
                None,
            )

        # Measured here because the file is already on disk; the alternative is
        # every browser rediscovering it by downloading the image, which is what
        # made the gallery reflow as it loaded.
        dimensions = read_image_dimensions(final_path)

        try:
            log.debug("upload.sending", filename=display_filename)
            result = upload_to_imgchest(final_path, upload_name=upload_name)
            if result:
                post_link, direct_link = result
                log.info("upload.succeeded", filename=display_filename)
                return direct_link, None, dimensions
            log.warning("upload.failed", filename=display_filename, reason="imgchest_no_result")
            return (
                None,
                f"{display_filename}: Image host did not return a link (unexpected). Try again.",
                None,
            )
        except ImgChestError as e:
            log.warning(
                "upload.failed", filename=display_filename, reason="imgchest_error", error=str(e)
            )
            return None, str(e), None
        except Exception as e:
            log.exception("upload.failed", filename=display_filename, reason="unexpected")
            return None, f"Error uploading {display_filename}: {str(e)}", None
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                log.debug("upload.temp_removed", path=temp_path)
            except Exception as cleanup_e:
                log.warning("upload.temp_orphaned", path=temp_path, error=str(cleanup_e))
        if conversion_created_new_file and os.path.exists(final_path):
            try:
                os.remove(final_path)
                log.debug("upload.temp_removed", path=final_path)
            except Exception as cleanup_e:
                log.warning("upload.temp_orphaned", path=final_path, error=str(cleanup_e))


@customs_bp.route("/api/customs", methods=["GET"])
def list_customs():
    """One page of the browse-customs list, searched and sorted server-side.

    The client used to hold the whole library in memory and filter it there,
    which is both wasteful now and unworkable later: the roster is meant to grow
    to tens of thousands of characters, at which point client-side filtering
    stops being an option.
    """
    args = request.args
    try:
        page = int(args.get("page", 1))
        per_page = int(args.get("per_page", 20))
    except ValueError:
        return jsonify({"error": "page and per_page must be integers"}), 400

    sort = args.get("sort", "recent")
    if sort not in db.CUSTOMS_SORT_KEYS:
        return jsonify({"error": f"sort must be one of: {', '.join(db.CUSTOMS_SORT_KEYS)}"}), 400

    try:
        return jsonify(
            db.list_characters_with_customs(
                query=args.get("q", ""),
                mode="series" if args.get("by") == "series" else "name",
                sort=sort,
                page=page,
                per_page=per_page,
            )
        )
    except Exception as e:
        log.exception("customs.list_failed")
        return jsonify({"error": str(e)}), 500


@customs_bp.route("/api/custom-image", methods=["POST"])
@rate_limited("upload")
def add_custom_image():
    try:
        if "character_name" not in request.form:
            return jsonify({"error": "Character name is required"}), 400

        char_name = request.form["character_name"].strip()
        ok, err = validate_character_name(char_name)
        if not ok:
            return jsonify({"error": err}), 400

        # Handle multiple files
        files = request.files.getlist("files")
        # If no 'files' list, check for single 'file'
        if not files and "file" in request.files:
            files = [request.files["file"]]

        if not files or (len(files) == 1 and files[0].filename == ""):
            return jsonify({"error": "No files selected"}), 400

        file_count = len([f for f in files if f.filename])
        log.info("upload.batch_started", character=char_name, files=file_count)

        uploaded_links = []
        uploaded_dimensions = {}
        errors = []
        processed = 0
        # Numbering continues from every image this character has ever had, not
        # just the ones still showing, so a removal cannot free a number for
        # reuse. See db.count_custom_images_ever.
        next_index = db.count_custom_images_ever(char_name) + 1

        for file in files:
            fn = file.filename
            if not fn:
                continue

            processed += 1
            log.debug(
                "upload.batch_progress",
                character=char_name,
                index=processed,
                total=file_count,
                filename=fn,
            )

            # Save temporarily (sanitized basename)
            safe_fn = _safe_stored_filename(fn)
            temp_path = os.path.join(".", "temp_custom_" + safe_fn)
            file.save(temp_path)

            direct_link, one_err, dimensions = _run_single_custom_upload_from_temp(
                temp_path, fn, upload_name=imgchest_filename(char_name, next_index)
            )
            if direct_link:
                next_index += 1
                uploaded_links.append(direct_link)
                if dimensions:
                    uploaded_dimensions[direct_link] = dimensions
                log.debug("upload.batch_item_ok", character=char_name, index=processed, filename=fn)
            else:
                errors.append(one_err or "Unknown error")
                log.info(
                    "upload.batch_item_failed", character=char_name, index=processed, filename=fn
                )

        log.info(
            "upload.batch_finished",
            character=char_name,
            succeeded=len(uploaded_links),
            failed=len(errors),
        )
        if not uploaded_links:
            main_error = errors[0] if errors else "No files were successfully uploaded"
            return jsonify({"error": main_error, "details": errors}), 500

        db.add_custom_images(
            char_name,
            uploaded_links,
            added_by=identity.current_identity().id,
            dimensions=uploaded_dimensions,
        )
        db.update_last_modified(char_name)
        log.info("customs.added", character=char_name, count=len(uploaded_links))

        return jsonify(
            {
                "success": True,
                "message": f"{len(uploaded_links)} images added",
                "links": uploaded_links,
                "errors": errors,
            }
        )
    except Exception as e:
        log.exception("customs.add_failed")
        return jsonify({"error": str(e), "details": [f"Server error: {type(e).__name__}"]}), 500


@customs_bp.route("/api/import-custom-images-from-urls", methods=["POST"])
@rate_limited("import_urls")
def import_custom_images_from_urls():
    """Fetch image URLs server-side (drag-from-web: Pinterest, etc.) and add as custom images."""
    try:
        data = request.get_json(silent=True) or {}
        char_name = (data.get("character_name") or "").strip()
        ok, err = validate_character_name(char_name)
        if not ok:
            return jsonify({"error": err}), 400
        urls = data.get("urls")
        if not isinstance(urls, list) or not urls:
            return jsonify({"error": "urls must be a non-empty array"}), 400
        urls = [str(u).strip() for u in urls if u]
        urls = _dedupe_import_urls_preserve_order(urls)[:MAX_IMPORT_URLS]
        if not urls:
            return jsonify({"error": "No valid URLs"}), 400

        uploaded_links = []
        uploaded_dimensions = {}
        errors = []
        next_index = db.count_custom_images_ever(char_name) + 1
        for idx, url in enumerate(urls):
            log.debug("import.fetching", index=idx + 1, total=len(urls), url=url[:200])
            try:
                temp_path, display_filename = _fetch_image_from_url_for_import(url)
            except ValueError as e:
                errors.append(f"{url}: {e}")
                continue
            except Exception as e:
                errors.append(f"{url}: {str(e)}")
                continue
            direct_link, one_err, dimensions = _run_single_custom_upload_from_temp(
                temp_path, display_filename, upload_name=imgchest_filename(char_name, next_index)
            )
            if direct_link:
                next_index += 1
                uploaded_links.append(direct_link)
                if dimensions:
                    uploaded_dimensions[direct_link] = dimensions
            else:
                errors.append(one_err or "Unknown error")

        log.info(
            "import.batch_finished",
            character=char_name,
            succeeded=len(uploaded_links),
            failed=len(errors),
        )
        if not uploaded_links:
            main_error = errors[0] if errors else "No images were imported"
            return jsonify({"error": main_error, "details": errors}), 500

        db.add_custom_images(
            char_name,
            uploaded_links,
            added_by=identity.current_identity().id,
            dimensions=uploaded_dimensions,
        )
        db.update_last_modified(char_name)
        log.info(
            "customs.added", character=char_name, count=len(uploaded_links), source="url_import"
        )

        return jsonify(
            {
                "success": True,
                "message": f"{len(uploaded_links)} images added",
                "links": uploaded_links,
                "errors": errors,
            }
        )
    except Exception as e:
        log.exception("import.failed")
        return jsonify({"error": str(e), "details": [f"Server error: {type(e).__name__}"]}), 500


@customs_bp.route("/api/custom-image/<path:char_name>", methods=["GET"])
def get_custom_images(char_name):
    """Active images for one character, annotated for the caller.

    Each entry carries `is_mine` and `hidden` because both are per-viewer: the
    client cannot work either out on its own, and ownership must be decided
    server-side regardless.
    """
    try:
        # Targeted query rather than loading every character's images and
        # discarding all but one, which is what the JSON-document layout forced.
        me = identity.current_identity()
        return jsonify(
            db.get_custom_image_rows(char_name, me.id, viewer_is_staff=me.is_moderator)
        )
    except Exception:
        log.exception("customs.read_failed")
    return jsonify([])


@customs_bp.route("/api/reorder-custom-images", methods=["POST"])
def reorder_custom_images():
    try:
        req_data = request.json
        char_name = req_data.get("character_name")
        new_order = req_data.get("new_order")
        if not char_name or not new_order:
            return jsonify({"error": "Missing required fields"}), 400

        if not db.reorder_custom_images(char_name, new_order):
            return jsonify({"error": "Character not found"}), 404
        db.update_last_modified(char_name)
        return jsonify({"message": "Order updated successfully"})

    except Exception as e:
        log.exception("customs.reorder_failed")
        return jsonify({"error": str(e)}), 500


@customs_bp.route("/api/delete-custom-image", methods=["POST"])
@rate_limited("remove")
def delete_custom_image():
    """Remove a single image. 403 when it is not the caller's to remove."""
    data = request.get_json()
    if not data or "character_name" not in data or "image_url" not in data:
        return jsonify({"error": "Missing data"}), 400
    char_name = data["character_name"]
    image_url = data["image_url"]
    me = identity.current_identity()

    try:
        report = db.remove_custom_images(
            char_name, [image_url], me.id, is_moderator=me.is_moderator
        )
        if report is None:
            return jsonify({"error": "Character not found"}), 404
        if report["missing"]:
            return jsonify({"error": "Image not found"}), 404
        if report["denied"]:
            return jsonify(
                {
                    "error": "You can only remove images you added. Hide it instead.",
                    "denied": report["denied"],
                }
            ), 403
        db.update_last_modified(char_name)
        return jsonify({"success": True, "message": "Image removed"})
    except Exception as e:
        log.exception("customs.remove_failed")
        return jsonify({"error": str(e)}), 500


@customs_bp.route("/api/delete-custom-images", methods=["POST"])
@rate_limited("remove")
def delete_custom_images():
    """Remove the caller's own images from a selection.

    Returns the full breakdown rather than a bare success, because a mixed
    selection is the normal case: the UI has to be able to say "removed 3, 2
    were not yours" instead of silently dropping half the request.
    """
    data = request.get_json()
    if not data or "character_name" not in data or "image_urls" not in data:
        return jsonify({"error": "Missing data"}), 400
    char_name = data["character_name"]
    image_urls = data["image_urls"]
    if not isinstance(image_urls, list):
        return jsonify({"error": "image_urls must be a list"}), 400
    me = identity.current_identity()

    try:
        report = db.remove_custom_images(char_name, image_urls, me.id, is_moderator=me.is_moderator)
        if report is None:
            return jsonify({"error": "Character not found"}), 404
        if report["removed"]:
            db.update_last_modified(char_name)
        return jsonify(
            {
                "success": True,
                "removed": report["removed"],
                "denied": report["denied"],
                "missing": report["missing"],
            }
        )
    except Exception as e:
        log.exception("customs.remove_failed")
        return jsonify({"error": str(e)}), 500


@customs_bp.route("/api/removed/<path:char_name>", methods=["GET"])
def get_removed_images(char_name):
    """The Removed drawer. Nothing is ever hard-deleted, so this is never empty
    by accident -- if an image is gone from the gallery it is in here."""
    try:
        return jsonify(db.get_removed_for(char_name))
    except Exception:
        log.exception("customs.removed_read_failed")
        return jsonify([])


@customs_bp.route("/api/restore-images", methods=["POST"])
@rate_limited("restore")
def restore_images():
    """Put removed images back.

    Open to anyone on purpose: restoring is not destructive, and a removal that
    was wrong should be cheap for the next person to undo.
    """
    data = request.get_json()
    if not data or "character_name" not in data or "image_urls" not in data:
        return jsonify({"error": "Missing data"}), 400
    if not isinstance(data["image_urls"], list):
        return jsonify({"error": "image_urls must be a list"}), 400

    try:
        restored = db.restore_custom_images(data["character_name"], data["image_urls"])
        if restored:
            db.update_last_modified(data["character_name"])
        return jsonify({"success": True, "restored": restored})
    except Exception as e:
        log.exception("customs.restore_failed")
        return jsonify({"error": str(e)}), 500


def _image_ids_from(data):
    """Validate an image_ids payload. Returns (ids, error_response)."""
    ids = data.get("image_ids")
    if not isinstance(ids, list):
        return None, (jsonify({"error": "image_ids must be a list"}), 400)
    try:
        return [int(i) for i in ids], None
    except (TypeError, ValueError):
        return None, (jsonify({"error": "image_ids must be integers"}), 400)


@customs_bp.route("/api/hide-images", methods=["POST"])
@rate_limited("hide")
def hide_images():
    """Hide images for the caller only.

    This is the pressure valve that removes the reason to delete other people's
    images: instant, unlimited, and with no effect on anyone else's view.
    """
    data = request.get_json() or {}
    ids, error = _image_ids_from(data)
    if error:
        return error
    try:
        return jsonify(
            {"success": True, "hidden": db.hide_images(identity.current_identity().id, ids)}
        )
    except Exception as e:
        log.exception("customs.hide_failed")
        return jsonify({"error": str(e)}), 500


@customs_bp.route("/api/unhide-images", methods=["POST"])
@rate_limited("hide")
def unhide_images():
    data = request.get_json() or {}
    ids, error = _image_ids_from(data)
    if error:
        return error
    try:
        return jsonify(
            {"success": True, "unhidden": db.unhide_images(identity.current_identity().id, ids)}
        )
    except Exception as e:
        log.exception("customs.unhide_failed")
        return jsonify({"error": str(e)}), 500


@customs_bp.route("/api/report-image", methods=["POST"])
@rate_limited("report")
def report_image():
    """Report an image for an objective problem.

    Objective only -- wrong character, dead link, NSFW, duplicate. Taste is what
    hide-for-me is for, and conflating the two is how a report queue turns into
    a popularity contest (DECISIONS.md section 1).
    """
    data = request.get_json() or {}
    image_id = data.get("image_id")
    reason = data.get("reason")
    if image_id is None or reason is None:
        return jsonify({"error": "Missing image_id or reason"}), 400
    try:
        image_id = int(image_id)
    except (TypeError, ValueError):
        return jsonify({"error": "image_id must be an integer"}), 400
    if reason not in db.REPORT_REASONS:
        return jsonify({"error": f"reason must be one of: {', '.join(db.REPORT_REASONS)}"}), 400

    try:
        result = db.report_image(image_id, identity.current_identity().id, reason)
        if result is None:
            return jsonify({"error": "Image not found"}), 404
        return jsonify({"success": True, **result})
    except Exception as e:
        log.exception("customs.report_failed")
        return jsonify({"error": str(e)}), 500


@customs_bp.route("/api/takes", methods=["POST"])
def record_takes():
    """Log that images were downloaded or copied into an $ai command.

    Fire-and-forget on purpose: this drives nothing, so a failure here must
    never surface to the user or block the action they actually asked for.
    """
    data = request.get_json() or {}
    kind = data.get("kind")
    ids, error = _image_ids_from(data)
    if error:
        return error
    if kind not in ("download", "copy_command"):
        return jsonify({"error": "kind must be 'download' or 'copy_command'"}), 400

    me = identity.current_identity()
    logged = 0
    for image_id in ids:
        try:
            if db.log_take(image_id, me.id, kind):
                logged += 1
        except Exception:
            log.exception("customs.take_failed", image_id=image_id)
    return jsonify({"success": True, "logged": logged})
