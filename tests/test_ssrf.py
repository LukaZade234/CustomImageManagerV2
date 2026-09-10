"""SSRF guards on the URL-import paths.

Two endpoints fetch a URL the caller supplies -- drag-an-image-from-the-web
import, and the Mudae image proxy. Both run on the origin, which sits inside a
private network with a cloud metadata service on it, so "fetch this URL for me"
is the highest-value thing an attacker can reach for.
"""

import ipaddress

import pytest

import remote_images
import upload_imgchest as app_module


class TestAddressClassification:
    @pytest.mark.parametrize(
        "address",
        [
            "127.0.0.1",
            "10.0.0.1",
            "192.168.1.1",
            "172.16.0.1",
            # Cloud metadata. The single most valuable SSRF target on any VM.
            "169.254.169.254",
            "0.0.0.0",
            "224.0.0.1",
            "::1",
            "fc00::1",
            "fe80::1",
        ],
    )
    def test_obvious_internal_addresses_are_blocked(self, address):
        assert remote_images._ip_is_blocked(ipaddress.ip_address(address))

    @pytest.mark.parametrize(
        ("address", "why"),
        [
            ("::ffff:127.0.0.1", "IPv4-mapped loopback"),
            ("::ffff:10.0.0.1", "IPv4-mapped private"),
            ("::ffff:169.254.169.254", "IPv4-mapped metadata"),
            ("fec0::1", "IPv6 site-local, which carries no stdlib flag"),
            ("100.64.0.1", "RFC 6598 carrier NAT, used for cloud internal networks"),
            ("198.18.0.1", "RFC 2544 benchmarking range"),
        ],
    )
    def test_the_ranges_the_stdlib_does_not_flag(self, address, why):
        """Each of these passed the original guard."""
        assert remote_images._ip_is_blocked(ipaddress.ip_address(address)), why

    @pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "2606:4700::1111"])
    def test_real_public_addresses_are_allowed(self, address):
        assert not remote_images._ip_is_blocked(ipaddress.ip_address(address))


class TestUrlValidation:
    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "gopher://example.com/",
            "ftp://example.com/x.png",
            "http://localhost/x.png",
            "http://127.0.0.1/x.png",
            "http://[::1]/x.png",
            "http://router.local/x.png",
            "http://169.254.169.254/latest/meta-data/",
            # Credentials in the URL are a smuggling vector, not a use case.
            "http://user:pass@example.com/x.png",
            "",
            "not a url",
        ],
    )
    def test_refused(self, url):
        assert remote_images._safe_import_image_url(url) is False

    def test_a_normal_https_image_url_is_allowed(self):
        assert remote_images._safe_import_image_url("https://cdn.imgchest.com/files/abc.png") is True


@pytest.fixture
def resolving(monkeypatch):
    """Make .example hostnames resolve to a public address.

    Without this the redirect tests never reach the code under test: the guard
    rejects an unresolvable hostname first, so every case would pass for the
    wrong reason.
    """
    real = remote_images.socket.getaddrinfo

    def fake(host, *args, **kwargs):
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if str(host).endswith(".example"):
                return [(0, 0, 0, "", ("93.184.216.34", 0))]
            return real(host, *args, **kwargs)
        return [(0, 0, 0, "", (host, 0))]

    monkeypatch.setattr(remote_images.socket, "getaddrinfo", fake)


class _Redirect:
    """Minimal stand-in for a requests redirect response."""

    is_redirect = True
    is_permanent_redirect = False
    status_code = 302

    def __init__(self, location):
        self.headers = {"Location": location}

    def close(self):
        pass


class _Ok:
    is_redirect = False
    is_permanent_redirect = False
    status_code = 200
    headers = {"Content-Type": "image/png"}
    content = b"png"

    def close(self):
        pass


class TestRedirectHops:
    """The original code followed the chain itself and checked only the final
    URL, so a hop through a private host was fetched before anything noticed."""

    def test_every_hop_is_validated_not_just_the_last(self, monkeypatch, resolving):
        requested = []

        def fake_get(url, **_kwargs):
            requested.append(url)
            # Public -> private -> public. The old check saw only the last URL.
            if url == "https://start.example/a.png":
                return _Redirect("http://169.254.169.254/latest/meta-data/")
            return _Ok()

        monkeypatch.setattr(remote_images.requests, "get", fake_get)
        with pytest.raises(ValueError, match="not allowed"):
            remote_images._get_with_validated_redirects("https://start.example/a.png", timeout=1)

        assert requested == ["https://start.example/a.png"], (
            "the private hop must never be requested"
        )

    def test_a_public_redirect_chain_still_works(self, monkeypatch, resolving):
        def fake_get(url, **_kwargs):
            if url == "https://start.example/a.png":
                return _Redirect("https://cdn.example/b.png")
            return _Ok()

        monkeypatch.setattr(remote_images.requests, "get", fake_get)
        response = remote_images._get_with_validated_redirects(
            "https://start.example/a.png", timeout=1
        )
        assert response.status_code == 200

    def test_a_redirect_loop_terminates(self, monkeypatch, resolving):
        monkeypatch.setattr(
            remote_images.requests,
            "get",
            lambda url, **_kwargs: _Redirect("https://cdn.example/loop.png"),
        )
        with pytest.raises(ValueError, match="Too many redirects"):
            remote_images._get_with_validated_redirects("https://cdn.example/loop.png", timeout=1)

    def test_a_redirect_with_no_location_is_an_error(self, monkeypatch, resolving):
        class _Headerless(_Redirect):
            def __init__(self):
                self.headers = {}

        monkeypatch.setattr(remote_images.requests, "get", lambda url, **_kw: _Headerless())
        with pytest.raises(ValueError, match="Redirect without a target"):
            remote_images._get_with_validated_redirects("https://cdn.example/a.png", timeout=1)

    def test_a_relative_redirect_is_resolved_against_the_current_url(self, monkeypatch, resolving):
        seen = []

        def fake_get(url, **_kwargs):
            seen.append(url)
            return _Redirect("/next.png") if len(seen) == 1 else _Ok()

        monkeypatch.setattr(remote_images.requests, "get", fake_get)
        remote_images._get_with_validated_redirects("https://cdn.example/a/b.png", timeout=1)
        assert seen[1] == "https://cdn.example/next.png"


class TestProxyEndpoint:
    def test_a_blocked_url_is_403_not_500(self, client, clean_db, identity_id, monkeypatch):
        monkeypatch.setattr(app_module.mudae_discord, "configured", lambda: True)
        r = client.get("/api/mudae/proxy-image?url=http://169.254.169.254/latest/meta-data/")
        assert r.status_code == 403

    def test_a_blocked_redirect_is_403_not_500(
        self, client, clean_db, identity_id, monkeypatch, resolving
    ):
        """A ValueError escaping as a 500 would leak that the guard even ran."""
        monkeypatch.setattr(app_module.mudae_discord, "configured", lambda: True)
        monkeypatch.setattr(
            remote_images.requests,
            "get",
            lambda url, **_kw: _Redirect("http://10.0.0.1/x.png"),
        )
        r = client.get("/api/mudae/proxy-image?url=https://cdn.imgchest.com/files/a.png")
        assert r.status_code == 403
        assert r.get_json()["error"] == "URL not allowed"
