"""Character catalog lookups for the Add flow.

Suggestions and the "is this name known, and what series is it in?" check read
the imported catalog and the working `characters` table -- never Discord. The
Add flow only falls back to `/api/mudae/lookup-character` when the catalog has
no answer, so a name already in the library costs no Mudae request.
"""

from __future__ import annotations

from flask import Blueprint, jsonify, request

import db
import logs
from ratelimit import rate_limited

log = logs.get(__name__)
catalog_bp = Blueprint("catalog", __name__)


def _int_arg(name: str, default: int, maximum: int) -> int:
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(1, min(maximum, value))


@catalog_bp.route("/api/catalog/characters", methods=["GET"])
@rate_limited("suggest")
def catalog_characters():
    """Name suggestions for the combobox, best-ranked first on an empty query.

    `series` narrows to one exact series, so a visitor who has already named the
    series is offered its characters. `pool` is a comma-separated list of pool
    facets (waifu, husbando, anime, game); every one named must hold.
    """
    pools = [p.strip().lower() for p in request.args.get("pool", "").split(",") if p.strip()]
    return jsonify(
        {
            "items": db.suggest_characters(
                request.args.get("q", ""),
                limit=_int_arg("limit", 10, 25),
                series=request.args.get("series", ""),
                pools=pools,
            )
        }
    )


@catalog_bp.route("/api/catalog/search", methods=["GET"])
@rate_limited("suggest")
def catalog_search():
    """One page of a catalog search, for the search results page.

    `by` is name or series, `sort` is rank/alphabet/count, and the page size is
    capped so a client cannot ask for the whole catalog in one request.
    """
    mode = request.args.get("by")
    sort = request.args.get("sort")
    order = request.args.get("order")
    return jsonify(
        db.search_catalog(
            request.args.get("q", ""),
            mode="series" if mode == "series" else "name",
            sort=sort if sort in ("rank", "alphabet", "count") else "rank",
            order="desc" if order == "desc" else "asc",
            page=_int_arg("page", 1, 100_000),
            per_page=_int_arg("per_page", 60, 100),
        )
    )


@catalog_bp.route("/api/catalog/series", methods=["GET"])
@rate_limited("suggest")
def catalog_series():
    """Series suggestions, drawn from the working set and the catalog."""
    return jsonify(
        {"items": db.suggest_series(request.args.get("q", ""), limit=_int_arg("limit", 20, 50))}
    )


@catalog_bp.route("/api/catalog/character", methods=["GET"])
@rate_limited("suggest")
def catalog_character():
    """The library's record for one name, used to offer and validate its series."""
    name = (request.args.get("name") or "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    found = db.find_character(name)
    return jsonify({"found": bool(found), "character": found})


@catalog_bp.route("/api/catalog/add-character", methods=["POST"])
@rate_limited("add_character")
def catalog_add_character():
    """Add a catalog character to the working set, with its Mudae portrait.

    No ImgChest upload and no Discord lookup: the catalog already holds both.
    """
    data = request.get_json(silent=True) or {}
    name = str(data.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Name is required"}), 400
    found = db.find_character(name)
    if not found:
        return jsonify({"error": f'"{name}" is not in the library'}), 404
    if found["in_library"]:
        return jsonify({"error": f'Character "{found["name"]}" already exists'}), 400
    try:
        if not db.add_character(found["name"], found["series"], found["rank"], found["image"]):
            return jsonify({"error": f'Character "{found["name"]}" already exists'}), 400
        db.update_last_modified(found["name"])
        return jsonify(
            {
                "success": True,
                "source": "catalog",
                "message": f'Added "{found["name"]}"',
                "character": found,
            }
        )
    except Exception:
        log.exception("catalog.add_failed")
        return jsonify({"error": "Failed to add character"}), 500
