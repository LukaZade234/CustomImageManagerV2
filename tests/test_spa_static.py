"""The SPA's static files, and the 404s that must survive serving them.

`routes/spa.py` enumerates client routes rather than using a catch-all, so that
a typo in an API path answers 404 instead of HTML the caller then fails to parse
as JSON. Adding static-file routes is exactly the change that could undo that,
so these tests pin both halves: the files are reachable, and everything else
still 404s.

The files come from `frontend/public/`, which Vite copies verbatim into
`frontend/dist/`. That directory is gitignored and only exists after a build, so
each test skips rather than fails when it is absent -- a missing build is not a
broken route.
"""

import os

import pytest

from routes import spa


def _dist(*parts):
    path = os.path.join(spa.SPA_DIR, *parts)
    if not os.path.exists(path):
        pytest.skip(f"{os.path.join(*parts)} absent; run `cd frontend && npm run build`")
    return path


@pytest.mark.parametrize(
    ("path", "content_type"),
    [
        ("/favicon.ico", "image"),
        ("/favicon-32.png", "image/png"),
        ("/apple-touch-icon.png", "image/png"),
        ("/robots.txt", "text/plain"),
    ],
)
def test_root_files_are_served(client, path, content_type):
    _dist(path.lstrip("/"))
    response = client.get(path)
    assert response.status_code == 200
    assert content_type in response.headers["Content-Type"]


@pytest.mark.parametrize("path", ["/emoji/female.webp", "/fonts/Geist-Variable.woff2"])
def test_public_folders_are_served(client, path):
    _dist(*path.lstrip("/").split("/"))
    assert client.get(path).status_code == 200


def test_unknown_root_file_is_not_a_file_lookup(client):
    """The root rule is an allowlist, so it cannot be used to read the tree."""
    assert client.get("/index.html").status_code == 404
    assert client.get("/package.json").status_code == 404


def test_public_folder_route_refuses_traversal(client):
    assert client.get("/fonts/../index.html").status_code == 404


@pytest.mark.parametrize("path", ["/api", "/api/not-a-real-endpoint", "/api/customs/nope"])
def test_unknown_api_paths_still_404(client, path):
    """The reason spa.py has no catch-all. A regression here returns HTML."""
    response = client.get(path)
    assert response.status_code == 404


def test_client_routes_still_serve_the_shell(client):
    _dist("index.html")
    for path in ("/", "/customs", "/character/Rem"):
        response = client.get(path)
        assert response.status_code == 200
        assert "text/html" in response.headers["Content-Type"]
