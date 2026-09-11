"""Every route the app has ever served, pinned.

This exists for the blueprint split. Moving 46 routes out of one module and into
six carries exactly one dangerous failure: a route that quietly does not
register. Flask does not complain — the endpoint simply 404s, and unless a test
happens to call that path, nothing notices until someone in production clicks
the thing that no longer works.

So the URL map itself is the assertion. A route that disappears, changes path,
or loses a method fails here rather than in production. Adding a route is meant
to require editing this list: that is the point, not an inconvenience.

`/static/<path:filename>` is Flask's own, registered by the Flask() constructor
rather than by us.
"""

import os

import upload_imgchest


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


EXPECTED_ROUTES = {
    ("/", "GET"),
    ("/add", "GET"),
    ("/api/add-character", "POST"),
    ("/api/auth/discord/callback", "GET"),
    ("/api/auth/discord/start", "GET"),
    ("/api/auth/logout", "POST"),
    ("/api/characters", "GET"),
    ("/api/characters/<path:name>/view", "POST"),
    ("/api/custom-image", "POST"),
    ("/api/custom-image/<path:char_name>", "GET"),
    ("/api/customs", "GET"),
    ("/api/delete-custom-image", "POST"),
    ("/api/delete-custom-images", "POST"),
    ("/api/download-image-proxy", "POST"),
    ("/api/edit-character", "POST"),
    ("/api/health", "GET"),
    ("/api/hide-images", "POST"),
    ("/api/import-custom-images-from-urls", "POST"),
    ("/api/last-updated", "GET"),
    ("/api/me", "GET"),
    ("/api/me/contributions", "GET"),
    ("/api/me/hidden", "GET"),
    ("/api/me/history", "GET"),
    ("/api/me/removed", "GET"),
    ("/api/me/settings", "PATCH"),
    ("/api/mudae/add-series", "POST"),
    ("/api/mudae/cancel-series", "POST"),
    ("/api/mudae/lookup-character", "POST"),
    ("/api/mudae/lookup-series", "POST"),
    ("/api/mudae/proxy-image", "GET"),
    ("/api/mudae/refresh-main-image", "POST"),
    ("/api/mudae/status", "GET"),
    ("/api/removed/<path:char_name>", "GET"),
    ("/api/reorder-custom-images", "POST"),
    ("/api/report-image", "POST"),
    ("/api/restore-images", "POST"),
    ("/api/saved", "GET"),
    ("/api/saved", "POST"),
    ("/api/saved/<path:name>", "DELETE"),
    ("/api/set-main-image", "POST"),
    ("/api/stats", "GET"),
    ("/api/takes", "POST"),
    ("/api/unhide-images", "POST"),
    ("/assets/<path:filename>", "GET"),
    ("/character/<path:name>", "GET"),
    ("/character_images/<path:filename>", "GET"),
    ("/characters", "GET"),
    ("/customs", "GET"),
    ("/images/<filename>", "GET"),
    ("/saved", "GET"),
    ("/static/<path:filename>", "GET"),
    ("/thumbs/<int:image_id>.webp", "GET"),
    ("/upload", "POST"),
}


def _actual_routes():
    """(path, method) for everything registered, HEAD and OPTIONS ignored.

    Flask adds those to every GET rule on its own, so including them would say
    nothing and would break the moment Flask changed that behaviour.
    """
    return {
        (rule.rule, method)
        for rule in upload_imgchest.app.url_map.iter_rules()
        for method in rule.methods
        if method not in ("HEAD", "OPTIONS")
    }


class TestUrlMap:
    def test_no_route_has_gone_missing(self):
        missing = EXPECTED_ROUTES - _actual_routes()
        assert not missing, f"routes no longer registered: {sorted(missing)}"

    def test_no_route_has_appeared_unannounced(self):
        """A new route is fine — but it has to be added here deliberately."""
        extra = _actual_routes() - EXPECTED_ROUTES
        assert not extra, f"new routes not listed in EXPECTED_ROUTES: {sorted(extra)}"

    def test_every_endpoint_resolves_to_a_real_view(self):
        """A blueprint registered twice, or not at all, shows up here."""
        for rule in upload_imgchest.app.url_map.iter_rules():
            assert rule.endpoint in upload_imgchest.app.view_functions, (
                f"{rule.rule} has no view function"
            )


class TestPathsSurviveTheModuleLayout:
    """Paths derived from `__file__` break when a file changes directory.

    The URL map cannot see this class of bug: the route registers perfectly and
    then serves the wrong thing. It happened during the blueprint split — the
    SPA routes moved into routes/, so `os.path.dirname(__file__)` stopped being
    the repo root and SPA_DIR silently became routes/frontend/dist. Every page
    of the app answered 503 while every test still passed.
    """

    def test_the_spa_directory_is_the_real_one(self):
        from routes import spa

        assert os.path.isdir(os.path.dirname(spa.SPA_DIR)), (
            f"SPA_DIR's parent does not exist: {spa.SPA_DIR}"
        )
        assert os.path.basename(os.path.dirname(spa.SPA_DIR)) == "frontend"
        assert spa.SPA_DIR.startswith(_repo_root()), f"SPA_DIR escaped the repo: {spa.SPA_DIR}"

    def test_static_images_resolve_from_the_app_root(self):
        """send_from_directory takes these relative to the app's root_path."""
        root = upload_imgchest.app.root_path
        assert os.path.isdir(os.path.join(root, "character_images")), (
            f"character_images not found under app.root_path={root}"
        )
