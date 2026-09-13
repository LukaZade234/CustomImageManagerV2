"""Parsing a Mudae `$wa` / `$ima` extract into catalog characters and series.

The input is plain text copied out of Mudae's listings, one block per series:

    【OSHI NO KO】 - 9/27
    #54 - Ai Hoshino · ($wa) - https://mudae.net/uploads/5711403/mwfbqTN~w5sjhP3.png

Nothing here may assume ASCII. Real extracts contain emoji series (a block
headed by `🤔`), CJK brackets (`【OSHI NO KO】`), braces and accents
(`{ tákt op. }`), fullwidth names, middle dots and hyphens inside a name, and
pools that list more than one tag (`$wa, $ha`). A single malformed line must be
recorded and skipped, never abort the run.

Extracts taken through a personal Mudae account also carry account-specific
noise between the name and the `·` separator, e.g. `Yoriko Kichijouji  🚫  $wa
DISABLED · ($wa)` or `Louise ... 🚫  ($serverdisable) · ($wa)`.
`strip_account_marker` removes it so it never lands in a name.

The same character is re-captured by many extracts, so parsing is followed by a
merge keyed on `name_key`, which folds every Unicode form SQLite's
`COLLATE NOCASE` cannot (NFC/NFD, fullwidth, NBSP). When two rows collide, the
better (lower) rank wins; identical repeats are simply dropped.

This module is deliberately free of the database and of Flask: it turns text
into dataclasses, and the caller decides what to persist.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from validation import MAX_RANK_LENGTH, MAX_SERIES_LENGTH, validate_character_name

# The series header: "Series name - listed/total". Non-greedy so a series whose
# own name contains a dash still matches at the final " - N/M".
_SERIES_RE = re.compile(r"^(?P<series>.+?)\s*-\s*(?P<listed>\d+)\s*/\s*(?P<total>\d+)\s*$")

# A character line. The name is greedy so it splits on the *last* "· (" -- which
# is what protects a name that itself contains a middle dot. The URL is anchored
# to the end, so trailing whitespace and the pool list can vary freely.
_CHAR_RE = re.compile(
    r"^#(?P<rank>[\d,]+)\s*-\s*(?P<name>.+)"
    r"\s*[·•]\s*\((?P<pools>[^)]*)\)\s*-\s*"
    r"(?P<url>https://mudae\.net/uploads/\S+\.png)\s*$"
)

_POOL_TOKEN_RE = re.compile(r"^\$([wh])([ag])$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_APOSTROPHES = {"\u2018": "'", "\u2019": "'", "\u02bc": "'", "\u2032": "'"}

# A character queried through a personal Mudae account can carry an
# account-specific marker between the name and the "· ($pool)" separator:
#   #11,203 - Yoriko Kichijouji  🚫  $wa  DISABLED · ($wa) - https://...
#   #1,395 - Louise Françoise Le Blanc de La Vallière 🚫  ($serverdisable) · ($wa) - ...
# The marker is noise, not part of the name: strip it. The emoji class spans the
# pictograph/dingbat/symbol ranges plus the variation selector and ZWJ, so it
# matches a lone 🚫 or a multi-codepoint symbol without ever eating a real word.
_MARKER_SYMBOL = (
    r"[\U0001F000-\U0001FAFF\u2190-\u2BFF\u2600-\u27BF\uFE0F\u200D\u20E3]"
)
_MARKER_TAILS = (
    r"\(\s*\$?serverdisable\s*\)",  # ($serverdisable) / (serverdisable)
    r"\$serverdisable",  # $serverdisable
    r"\$[a-z]{2}\s+DISABLED",  # $wa DISABLED
)
_DISABLED_MARKER_RE = re.compile(
    rf"\s*(?:{_MARKER_SYMBOL}+\s*)*(?:{'|'.join(_MARKER_TAILS)})\s*$",
    re.IGNORECASE,
)


def strip_account_marker(name: str) -> str:
    """Drop a trailing account marker ("🚫 $wa DISABLED", "🚫 ($serverdisable)")."""
    return _DISABLED_MARKER_RE.sub("", name).strip()

# An unranked or unparseable rank is treated as worse than every real rank, so a
# duplicate that *does* have a rank always wins the merge.
_NO_RANK = 10**12


def name_key(value: str) -> str:
    """The Unicode-folded match key for a name or series.

    NFKC folds fullwidth and compatibility forms; curly apostrophes become
    straight; NBSP and any run of whitespace collapse to one space; casefold is
    the Unicode-aware form of lower(). Two spellings that differ only in these
    ways refer to the same character and must not create two catalog rows.
    """
    text = unicodedata.normalize("NFKC", value or "")
    text = text.replace("\u00a0", " ")
    text = "".join(_APOSTROPHES.get(ch, ch) for ch in text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text.casefold()


def _rank_value(rank: str) -> int:
    return int(rank) if rank.isdigit() else _NO_RANK


@dataclass(frozen=True, slots=True)
class CatalogCharacter:
    name: str
    series: str
    rank: str  # digits only, commas stripped; "" when the extract had none
    image_url: str
    pool: str  # normalised, e.g. "wa,wg"; "" when unknown
    is_waifu: bool = False
    is_husbando: bool = False
    is_anime: bool = False
    is_game: bool = False


@dataclass(frozen=True, slots=True)
class CatalogSeries:
    series: str
    listed: int | None
    total: int | None


@dataclass(frozen=True, slots=True)
class ParseIssue:
    source: str
    line_no: int
    text: str
    reason: str


@dataclass
class ParseResult:
    """Characters keyed by name_key, series keyed by series key."""

    characters: dict[str, CatalogCharacter] = field(default_factory=dict)
    series: dict[str, CatalogSeries] = field(default_factory=dict)
    issues: list[ParseIssue] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    lines_total: int = 0
    lines_parsed: int = 0
    # A character seen again, unchanged. Expected in bulk: extracts overlap.
    duplicates: int = 0
    # A character seen again with different data; the better rank won.
    conflicts: int = 0


def parse_pools(raw: str) -> tuple[str, bool, bool, bool, bool, list[str]]:
    """Parse a raw pool list into (normalised, waifu, husbando, anime, game, unknown).

    Accepts the real forms `$wa`, `$wg`, `$ha`, `$hg`, and comma-separated
    combinations. Unknown tags are returned rather than raising, so a new Mudae
    pool does not lose the character that carries it.
    """
    codes: set[str] = set()
    unknown: list[str] = []
    for token in (raw or "").split(","):
        token = token.strip()
        if not token:
            continue
        match = _POOL_TOKEN_RE.match(token)
        if not match:
            unknown.append(token)
            continue
        codes.add(f"{match.group(1).lower()}{match.group(2).lower()}")
    ordered = sorted(codes)
    return (
        ",".join(ordered),
        any(code[0] == "w" for code in ordered),
        any(code[0] == "h" for code in ordered),
        any(code[1] == "a" for code in ordered),
        any(code[1] == "g" for code in ordered),
        unknown,
    )


def _store_character(result: ParseResult, character: CatalogCharacter) -> None:
    key = name_key(character.name)
    existing = result.characters.get(key)
    if existing is None:
        result.characters[key] = character
        return
    if existing == character:
        result.duplicates += 1
        return
    # Same character, different capture. Keep the better rank; ties keep the
    # first, so an extract order change cannot silently reshuffle the catalog.
    if _rank_value(character.rank) < _rank_value(existing.rank):
        result.characters[key] = character
    result.conflicts += 1


def _store_series(result: ParseResult, series: CatalogSeries) -> None:
    key = name_key(series.series)
    existing = result.series.get(key)
    if existing is None:
        result.series[key] = series
        return
    # Extracts cover a series in different depths; keep the widest coverage.
    listed = max(existing.listed or 0, series.listed or 0) or None
    total = max(existing.total or 0, series.total or 0) or None
    result.series[key] = CatalogSeries(series.series, listed, total)


def parse_into(result: ParseResult, text: str, *, source: str = "") -> ParseResult:
    """Parse one extract into `result`, merging with what is already there."""
    if source and source not in result.sources:
        result.sources.append(source)

    # A BOM survives utf-8 decoding if a caller read bytes another way; it is not
    # whitespace, so it would otherwise become part of the first series name.
    text = text.lstrip("\ufeff")

    current_series = ""
    for line_no, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line:
            continue
        result.lines_total += 1

        if line.startswith("#"):
            match = _CHAR_RE.match(line)
            if not match:
                result.issues.append(
                    ParseIssue(source, line_no, line, "not a character line")
                )
                continue
            name = strip_account_marker(match.group("name").strip())
            ok, err = validate_character_name(name)
            if not ok:
                result.issues.append(ParseIssue(source, line_no, line, err or "invalid name"))
                continue
            rank = match.group("rank").replace(",", "").strip()
            if len(rank) > MAX_RANK_LENGTH:
                result.issues.append(
                    ParseIssue(source, line_no, line, "rank too long")
                )
                continue
            series = current_series[:MAX_SERIES_LENGTH]
            pool, waifu, husbando, anime, game, unknown = parse_pools(match.group("pools"))
            if unknown:
                result.issues.append(
                    ParseIssue(source, line_no, line, f"unknown pool tag(s): {', '.join(unknown)}")
                )
            _store_character(
                result,
                CatalogCharacter(
                    name=name,
                    series=series,
                    rank=rank,
                    image_url=match.group("url"),
                    pool=pool,
                    is_waifu=waifu,
                    is_husbando=husbando,
                    is_anime=anime,
                    is_game=game,
                ),
            )
            result.lines_parsed += 1
            continue

        match = _SERIES_RE.match(line)
        if not match:
            result.issues.append(ParseIssue(source, line_no, line, "not a series header"))
            continue
        current_series = match.group("series").strip()
        _store_series(
            result,
            CatalogSeries(
                series=current_series,
                listed=int(match.group("listed")),
                total=int(match.group("total")),
            ),
        )
        result.lines_parsed += 1

    return result


def parse_text(text: str, *, source: str = "") -> ParseResult:
    """Parse a single extract. Thin wrapper over `parse_into` for callers."""
    return parse_into(ParseResult(), text, source=source)


def parse_sources(sources: list[tuple[str, str]]) -> ParseResult:
    """Parse and merge many extracts given as (name, text) pairs.

    A character appearing in several extracts is collapsed here, so the caller
    can persist the result once and be sure the input was full of overlap.
    """
    result = ParseResult()
    for name, text in sources:
        parse_into(result, text, source=name)
    return result


def as_catalog_rows(result: ParseResult) -> list[dict]:
    """Shape merged characters for `db.upsert_catalog_characters`."""
    return [
        {
            "name": character.name,
            "name_key": key,
            "series": character.series,
            "rank": character.rank,
            "mudae_image_url": character.image_url,
            "pool": character.pool,
            "is_waifu": character.is_waifu,
            "is_husbando": character.is_husbando,
            "is_anime": character.is_anime,
            "is_game": character.is_game,
        }
        for key, character in result.characters.items()
    ]


def as_series_rows(result: ParseResult) -> list[dict]:
    """Shape merged series for `db.upsert_catalog_series`."""
    return [
        {"series": series.series, "listed": series.listed, "total": series.total}
        for series in result.series.values()
    ]


def as_catalog_map(result: ParseResult) -> dict[str, dict]:
    """Shape merged characters as the enrichment preview map db expects."""
    return {
        key: {
            "series": character.series,
            "rank": character.rank,
            "mudae_image_url": character.image_url,
        }
        for key, character in result.characters.items()
    }

