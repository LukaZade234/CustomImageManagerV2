"""Limits and checks on the character fields a caller can supply.

Kept apart from `remote_images`, which is about fetching bytes from the
internet safely. This is about text a person typed: how long it may be, and
what it may not contain. Both the ordinary character routes and the Mudae
import path enforce the same rules, which is the reason it is a module rather
than a private helper on either one.
"""

from __future__ import annotations

MAX_CHAR_NAME_LENGTH = 200
MAX_SERIES_LENGTH = 300
MAX_RANK_LENGTH = 50


def validate_character_name(name: str | None) -> tuple[bool, str | None]:
    """Returns (True, None) or (False, error_message).

    The path checks matter more than the length one: a character name becomes a
    filename and a URL segment, so `..` and slashes have to be refused here
    rather than sanitised later.
    """
    if not name or not name.strip():
        return False, "Name cannot be empty"
    s = name.strip()
    if len(s) > MAX_CHAR_NAME_LENGTH:
        return False, f"Name too long (max {MAX_CHAR_NAME_LENGTH} characters)"
    if ".." in s or "/" in s or "\\" in s:
        return False, "Name contains invalid characters"
    if any(ord(c) < 32 and c not in "\t\n\r" for c in s):
        return False, "Name contains invalid control characters"
    return True, None
