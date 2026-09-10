"""Getting an image from somewhere on the internet, safely.

Everything the app fetches on a visitor's behalf goes through here: dragging an
image in from a web page, the download proxy, and Mudae's card images. That
makes it the app's SSRF surface, so the guards live in one module rather than
being restated at each call site.

Also holds the naming rules for what lands on ImgChest, which are a filesystem
concern rather than a routing one.
"""

from __future__ import annotations

import ipaddress
import os
import re
import socket
import unicodedata
import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from werkzeug.utils import secure_filename


def _safe_stored_filename(original_filename: str) -> str:
    """Basename for temp files on disk — strips path segments and unsafe chars."""
    base = secure_filename(original_filename or "") or ""
    if not base:
        base = f"upload_{uuid.uuid4().hex[:12]}"
    return base


def _slug(text: str, limit: int = 40) -> str:
    """A filename-safe fragment of a character name.

    Unicode is folded rather than dropped, so 'Frédérica' stays readable instead
    of collapsing to 'frdrica'.
    """
    folded = unicodedata.normalize("NFKD", text or "")
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return (cleaned or "unknown")[:limit].strip("-")


def imgchest_filename(character_name: str, index: int | None = None, kind: str = "") -> str:
    """What the image is called on ImgChest.

    Every upload used to arrive there as `temp_custom_web_import_a1b2c3d4.png`,
    which is unusable if you ever need to find something in that account. The
    name now carries what you would sort or search by: which character it belongs
    to, its position in that character's gallery, and when it was added.

    The index counts every image the character has ever had, so it never repeats
    even after removals. It is therefore "the nth image ever added to Lucy"
    rather than "the nth in the gallery right now" — the two diverge once
    anything is removed, and since an ImgChest name is fixed at upload time and
    can never be corrected, the stable one is the useful one.
    """
    parts = [_slug(character_name)]
    if kind:
        parts.append(kind)
    if index is not None:
        parts.append(f"{index:03d}")
    parts.append(datetime.now(UTC).strftime("%Y%m%d"))
    return "-".join(parts) + ".png"


# Max file size (30MB) - reject larger files to avoid memory issues
MAX_FILE_SIZE = 30 * 1024 * 1024
# Drag-from-web: max image URLs per request
MAX_IMPORT_URLS = 20

# Allowed image extensions
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}

# Character name validation
MAX_CHAR_NAME_LENGTH = 200
MAX_SERIES_LENGTH = 300
MAX_RANK_LENGTH = 50

# Match frontend dragImageUrls.js — strip when deduping web import batches
_IMPORT_URL_TRACKING_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "fbclid",
        "gclid",
        "_ga",
        "mc_eid",
        "igshid",
        "ref",
        "ref_src",
        "spm",
        "spm_id",
    }
)


def _canonical_url_key_for_dedup(url):
    """Fragment + tracking params removed for stable equality (same image, different query strings)."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return (url or "").strip()
        netloc = (p.netloc or "").lower()
        pairs = [
            (k, v)
            for k, v in parse_qsl(p.query, keep_blank_values=True)
            if k.lower() not in _IMPORT_URL_TRACKING_PARAMS
        ]
        pairs.sort(key=lambda x: (x[0].lower(), x[1]))
        query = urlencode(pairs)
        return urlunparse((p.scheme, netloc, p.path, p.params, query, ""))
    except Exception:
        return (url or "").split("#")[0].strip()


def _dedupe_import_urls_preserve_order(urls):
    seen = set()
    out = []
    for u in urls:
        if not u:
            continue
        key = _canonical_url_key_for_dedup(u)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def _allowed_image_proxy_url(url):
    """Only ImgChest hosts — same URLs we store from upload_to_imgchest (avoids CORS + SSRF)."""
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        h = (p.hostname or "").lower()
        return h == "imgchest.com" or h.endswith(".imgchest.com")
    except Exception:
        return False


# Ranges the stdlib does not flag but that must not be reachable from the origin.
# `ipaddress` has no predicate for either.
_EXTRA_BLOCKED_NETWORKS = (
    # RFC 6598 carrier-grade NAT. Cloud providers use it for internal networks,
    # so it is a live SSRF target, not a theoretical one.
    ipaddress.ip_network("100.64.0.0/10"),
    # RFC 2544 benchmarking range.
    ipaddress.ip_network("198.18.0.0/15"),
)

# Enough to reach any legitimate CDN; far short of a redirect loop.
_MAX_IMPORT_REDIRECTS = 5


def _ip_is_blocked(ip):
    """True for anything that is not a public, routable internet address."""
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return True
    if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return True
    # IPv6 site-local (fec0::/10). Deprecated, still routable on some networks,
    # and carries none of the flags above.
    if getattr(ip, "is_site_local", False):
        return True
    # An IPv4-mapped IPv6 address has to be judged as the IPv4 address it
    # carries, or ::ffff:10.0.0.1 walks straight through.
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None and _ip_is_blocked(mapped):
        return True
    return any(net.version == ip.version and ip in net for net in _EXTRA_BLOCKED_NETWORKS)


def _host_resolves_only_to_public_ips(hostname):
    """Block SSRF: reject if any resolved address is loopback, private, link-local, etc.

    Residual risk, documented rather than fixed: this resolves the name, and then
    `requests` resolves it again when it connects. A hostile DNS server can
    answer public here and private there. Closing that needs connecting to a
    pinned address with the Host header set by hand, which is a larger change
    than it looks; the redirect handling below closes the cheaper variant of the
    same trick.
    """
    try:
        hostname = (hostname or "").lower().rstrip(".")
        if not hostname or hostname == "localhost":
            return False
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if not infos:
            return False
        for res in infos:
            if _ip_is_blocked(ipaddress.ip_address(res[4][0])):
                return False
    except Exception:
        return False
    return True


def _safe_import_image_url(url):
    """
    Allow https/http image URLs from the public internet for drag-from-web import.
    Stricter than ImgChest-only proxy: still blocks obvious SSRF targets.
    """
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        if p.username or p.password:
            return False
        h = (p.hostname or "").lower()
        if not h:
            return False
        if h in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        if h.endswith(".local") or h.endswith(".localhost"):
            return False
        if h.startswith("169.254."):  # link-local literal in hostname (unusual)
            return False
        if not _host_resolves_only_to_public_ips(h):
            return False
        return True
    except Exception:
        return False


def _request_headers_for_image_import(url):
    """
    Headers for fetching remote images. Pixiv CDN (pximg.net) returns 403 without a pixiv Referer.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
    }
    try:
        host = (urlparse(url).hostname or "").lower()
        if host.endswith("pximg.net") or host.endswith("pixiv.net") or host.endswith("pixiv.me"):
            # Per-artwork Referer when path includes Pixiv illustration id (e.g. .../119107915_p0.jpg)
            m = re.search(r"/(\d{6,})_p\d+", url)
            if m:
                headers["Referer"] = f"https://www.pixiv.net/artworks/{m.group(1)}"
            else:
                headers["Referer"] = "https://www.pixiv.net/"
    except Exception:
        pass
    return headers


def _guess_ext_from_response(content_type, final_url):
    ct = (content_type or "").lower()
    if "png" in ct:
        return ".png"
    if "jpeg" in ct or "jpg" in ct:
        return ".jpg"
    if "gif" in ct:
        return ".gif"
    if "webp" in ct:
        return ".webp"
    if "bmp" in ct:
        return ".bmp"
    path = urlparse(final_url).path.lower()
    for ext in ALLOWED_IMAGE_EXTENSIONS:
        if path.endswith(ext):
            return ext
    return ".png"


def _get_with_validated_redirects(url, **kwargs):
    """GET a URL, validating **every** hop rather than only the last one.

    `allow_redirects=True` follows the chain itself and hands back the final
    URL, so a chain of public -> 192.168.1.1 -> public passed validation while
    the request to the private host had already been made. Stepping the chain by
    hand is the only way to check each target before it is fetched.

    Returns the final response; the caller still owns closing it.
    """
    current = url
    for _ in range(_MAX_IMPORT_REDIRECTS + 1):
        if not _safe_import_image_url(current):
            raise ValueError("URL not allowed or blocked (private hosts are not permitted)")
        response = requests.get(
            current, headers=_request_headers_for_image_import(current), **kwargs
        )
        if not response.is_redirect and not response.is_permanent_redirect:
            return response
        location = response.headers.get("Location")
        response.close()
        if not location:
            raise ValueError("Redirect without a target")
        current = urljoin(current, location)
    raise ValueError("Too many redirects")


def _fetch_image_from_url_for_import(url):
    """
    Download remote image to a temp file. Validates URL before and after redirects.
    Returns (temp_path, display_filename) or raises ValueError.
    """
    r = _get_with_validated_redirects(url, timeout=60, allow_redirects=False, stream=True)
    if r.status_code != 200:
        raise ValueError(f"Image server returned HTTP {r.status_code}")
    total = 0
    chunks = []
    for chunk in r.iter_content(chunk_size=65536):
        if chunk:
            total += len(chunk)
            if total > MAX_FILE_SIZE + 2 * 1024 * 1024:
                raise ValueError("Image too large")
            chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        raise ValueError("Empty response")
    ext = _guess_ext_from_response(r.headers.get("Content-Type", ""), r.url)
    safe = f"web_import_{uuid.uuid4().hex[:12]}{ext}"
    temp_path = os.path.join(".", "temp_custom_" + safe)
    with open(temp_path, "wb") as f:
        f.write(raw)
    return temp_path, safe

