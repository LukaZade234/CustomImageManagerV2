import json
import os
import random
import time

import requests
from requests.exceptions import ConnectionError as RequestsConnectionError


class ImgChestError(Exception):
    """Raised when ImgChest API fails (rate limit, service down, etc)."""
    pass


API_KEY = os.environ.get("IMGCHEST_API_KEY", "")

# Max characters to embed in user-facing errors (avoids multi-MB accidental paste).
_MAX_ERROR_BODY_LEN = 8000

# Transient failures: retry with backoff before surfacing to the user.
_IMGCHEST_MAX_ATTEMPTS = 4
_RETRYABLE_HTTP = frozenset({502, 503, 504})

# Connect + read timeouts so the worker does not hang until a proxy kills the connection.
_IMGCHEST_POST_TIMEOUT = (30, 120)


def _log(msg):
    print(f"[IMGCHEST] {msg}", flush=True)


def _backoff_seconds(attempt_index):
    return (2 ** attempt_index) + random.uniform(0, 0.35)


def _error_detail_from_response(response):
    """User-facing detail from ImgChest (no truncation to a few hundred chars)."""
    raw = (response.text or "").strip()
    if not raw:
        return ""
    try:
        data = response.json()
        if isinstance(data, dict):
            for key in ("message", "error", "errors"):
                v = data.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()[:_MAX_ERROR_BODY_LEN]
                if isinstance(v, list) and v and isinstance(v[0], str):
                    return "; ".join(v)[:_MAX_ERROR_BODY_LEN]
        out = json.dumps(data, ensure_ascii=False)
        return out[:_MAX_ERROR_BODY_LEN]
    except (json.JSONDecodeError, TypeError, ValueError):
        return raw.replace("\n", " ")[:_MAX_ERROR_BODY_LEN]


def _size_clause_mb(file_size_mb, limit_mb=30.0):
    return f" Uploaded file size is {file_size_mb:.2f} MB; ImgChest allows at most {limit_mb:.0f} MB."


def upload_to_imgchest(file_path):
    if API_KEY == "YOUR_API_KEY_HERE" or not API_KEY:
        _log("ERROR: API_KEY not set")
        raise ImgChestError("Image hosting API key not configured. Set IMGCHEST_API_KEY environment variable.")

    if not os.path.exists(file_path):
        _log(f"ERROR: File not found: {file_path}")
        return None

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    _log(f"upload start: {file_path} ({file_size_mb:.2f} MB)")

    url = "https://api.imgchest.com/v1/post"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {
        "title": os.path.basename(file_path),
        "privacy": "hidden",
        "nsfw": "false",
    }

    response = None
    for attempt in range(_IMGCHEST_MAX_ATTEMPTS):
        try:
            with open(file_path, "rb") as image_file:
                files = {"images[]": image_file}
                _log(f"sending POST to api.imgchest.com (attempt {attempt + 1}/{_IMGCHEST_MAX_ATTEMPTS})...")
                response = requests.post(
                    url, headers=headers, data=payload, files=files, timeout=_IMGCHEST_POST_TIMEOUT
                )
        except requests.Timeout as e:
            _log(f"upload TIMEOUT (attempt {attempt + 1}): {type(e).__name__}: {e}")
            if attempt < _IMGCHEST_MAX_ATTEMPTS - 1:
                delay = _backoff_seconds(attempt)
                _log(f"retrying after {delay:.2f}s")
                time.sleep(delay)
                continue
            raise ImgChestError(
                "Image hosting timed out while uploading after multiple attempts. Your network may be slow, the file may be large, or the service may be busy — try again later or use a smaller image."
            )
        except RequestsConnectionError as e:
            _log(f"upload CONNECTION ERROR (attempt {attempt + 1}): {type(e).__name__}: {e}")
            if attempt < _IMGCHEST_MAX_ATTEMPTS - 1:
                delay = _backoff_seconds(attempt)
                _log(f"retrying after {delay:.2f}s")
                time.sleep(delay)
                continue
            raise ImgChestError(
                "Could not reach image hosting after multiple attempts. Please check your connection and try again."
            )
        except ImgChestError:
            raise
        except requests.RequestException as e:
            _log(f"upload REQUEST EXCEPTION: {type(e).__name__}: {e}")
            raise ImgChestError("Could not reach image hosting. Please check your connection and try again.")

        if response is None:
            continue

        status = response.status_code
        _log(f"response status: {status}")

        if status == 200:
            data = response.json()

            if "data" not in data:
                _log(
                    f"unexpected response (no 'data' key): {list(data.keys()) if isinstance(data, dict) else type(data)}"
                )
                raise ImgChestError("Image hosting returned invalid response")

            img_data = data["data"]

            post_link = img_data.get("url")
            if not post_link:
                _log(f"note: 'url' key missing in response, keys: {list(img_data.keys())}")
                post_link = "Not found in response"

            if "images" in img_data and len(img_data["images"]) > 0:
                direct_link = img_data["images"][0]["link"]
            else:
                direct_link = "No direct link found"
                _log("WARNING: no images in response")

            _log(
                f"upload SUCCESS: direct_link={direct_link[:80]}{'...' if len(direct_link) > 80 else ''}"
            )
            return post_link, direct_link

        if status == 429:
            if attempt < _IMGCHEST_MAX_ATTEMPTS - 1:
                delay = 4.0 + _backoff_seconds(attempt)
                _log(f"rate limited (429), sleeping {delay:.2f}s before retry")
                time.sleep(delay)
                continue
            raise ImgChestError("Image hosting rate limit reached. Please try again in a few minutes.")

        if status in _RETRYABLE_HTTP and attempt < _IMGCHEST_MAX_ATTEMPTS - 1:
            delay = _backoff_seconds(attempt)
            body_preview = (response.text or "")[:500]
            _log(f"retryable HTTP {status}, sleeping {delay:.2f}s; body preview: {body_preview!r}")
            time.sleep(delay)
            continue

        if status >= 500:
            detail = _error_detail_from_response(response)
            _log(f"upload FAILED: server error {status}, body={response.text[:500]}")
            extra = f" {detail}" if detail else ""
            raise ImgChestError(
                f"Image hosting returned server error {status}.{extra} Please try again later."
            )

        detail = _error_detail_from_response(response)
        _log(f"upload FAILED: status={status}, body={response.text[:500]}")
        size_note = _size_clause_mb(file_size_mb) if status == 400 else ""
        if detail:
            raise ImgChestError(
                f"Image hosting rejected the upload (HTTP {status}): {detail}.{size_note}"
            )
        raise ImgChestError(
            f"Image hosting rejected the upload (HTTP {status}).{size_note} Please try again later."
        )
