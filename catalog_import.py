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

from validation import MAX_CHAR_NAME_LENGTH, MAX_RANK_LENGTH, MAX_SERIES_LENGTH

# The series header: "Series name - listed/total". Non-greedy so a series whose
# own name contains a dash still matches at the final " - N/M". Commas are
# allowed in the counts; Mudae writes large totals as "1,018".
_SERIES_RE = re.compile(
    r"^(?P<series>.+?)\s*-\s*(?P<listed>[\d,]+)\s*/\s*(?P<total>[\d,]+)\s*$"
)

# The DM `$imartsmi- <series>` sends writes the header without the " - " the
# pasted extracts use: "Lord of the Mysteries   0/55". An alias line never ends
# in "digits/digits", so anchoring the pattern to the end keeps it unambiguous.
_SERIES_DM_RE = re.compile(
    r"^(?P<series>.+?)\s+(?P<listed>[\d,]+)\s*/\s*(?P<total>[\d,]+)\s*$"
)

# Mudae's DM is Discord markdown: the header and rank are bold (`**#4,252**`),
# pools are italic (`*($ha)*`), and the portrait is wrapped in `<>` to suppress a
# link preview. The paste extracts are plain, so only the DM path strips these.
_DM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
# Only `*` and backticks: `~` and `_` occur inside mudae.net filenames and names
# (`V40OZzn~uUp4hS7.png`), so stripping them would corrupt the portrait URL.
_DM_MARKUP_RE = re.compile(r"[*`]+")
_DM_ANGLE_RE = re.compile(r"[<>]")


def _clean_dm_line(raw: str) -> str:
    text = (raw or "").replace("\u200b", "")
    text = _DM_EMOJI_RE.sub("", text)
    text = _DM_ANGLE_RE.sub("", text)
    text = _DM_MARKUP_RE.sub("", text)
    return text.strip()

# A character line. The name is greedy so it splits on the *last* "· (" -- which
# is what protects a name that itself contains a middle dot. The URL is anchored
# to the end, so trailing whitespace and the pool list can vary freely. A stray
# "*" sometimes trails the pool list ("·($wa)*"), so allow it.
_CHAR_RE = re.compile(
    r"^#(?P<rank>[\d,]+)\s*-\s*(?P<name>.+)"
    r"\s*[·•]\s*\((?P<pools>[^)]*)\)\s*\**\s*-\s*"
    r"(?P<url>https://mudae\.net/uploads/\S+\.png)\s*$"
)

_POOL_TOKEN_RE = re.compile(r"^\$([wh])([ag])$", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")
_APOSTROPHES = {"\u2018": "'", "\u2019": "'", "\u02bc": "'", "\u2032": "'"}

# Lines that are neither a series header nor a character line and carry no data
# at all: the paste picks up Discord's own chrome ("Mudae", "APP", "— 16:47").
# Counted separately from real parse failures so the report is not noisy.
_NOISE_RE = re.compile(r"^(?:Mudae|APP|—\s*\d{1,2}:\d{2}(?::\d{2})?)\s*$")

# A character queried through a personal Mudae account can carry an
# account-specific marker between the name and the "· ($pool)" separator:
#   #11,203 - Yoriko Kichijouji  🚫  $wa  DISABLED · ($wa) - https://...
#   #1,395 - Louise Françoise Le Blanc de La Vallière 🚫  ($serverdisable) · ($wa) - ...
# The marker is noise, not part of the name: strip it. The emoji class is kept
# to the pictograph/dingbat/misc-symbol ranges (not U+2190-U+25FF) so it can
# never eat a name made of geometric shapes such as "▲▲▲▲▲▲▲".
_MARKER_SYMBOL = r"[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D\u20E3]"
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
    """Drop trailing account markers ("🚫 $wa DISABLED", "🚫 ($serverdisable)").

    A character disabled in several pools carries one marker per pool
    ("... 🚫 $wa DISABLED 🚫 $ha DISABLED"), so strip repeatedly rather than
    once; a single pass would leave every marker but the last in the name.
    """
    previous = None
    while previous != name:
        previous = name
        name = _DISABLED_MARKER_RE.sub("", name).strip()
    return name


def validate_catalog_name(name: str) -> tuple[bool, str | None]:
    """Length and control characters only, not the filename rules.

    `validate_character_name` refuses "/" because a working character's name
    becomes a filename and a URL segment. Catalog names are display data, and
    real Mudae names carry slashes ("Rin Tohsaka (F/EX)", "SP//dr (Peni
    Parker)"), so those are kept here; the filename rule applies later, only if
    a catalog row is ever promoted to a working character.
    """
    if not name or not name.strip():
        return False, "empty name"
    if len(name) > MAX_CHAR_NAME_LENGTH:
        return False, f"name too long (max {MAX_CHAR_NAME_LENGTH})"
    if any(ord(ch) < 32 for ch in name):
        return False, "control characters"
    # "/" is allowed (real names carry it, e.g. "SP//dr"), but a path-traversal
    # sequence is not. A bare ".." substring is not the test: real names contain
    # it ("You're Bald...") -- only ".." next to a separator is.
    if name in (".", "..") or re.search(r"\.\.[/\\]|[/\\]\.\.", name):
        return False, "name contains a path traversal"
    return True, None

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
    # Non-data lines (Discord chrome), reported separately from real failures.
    noise: int = 0
    # A character seen again, unchanged. Expected in bulk: extracts overlap.
    duplicates: int = 0
    # A character seen again with different data; the better rank won.
    conflicts: int = 0


@dataclass
class SeriesExtract:
    """One `$imartsmi-` DM body: its series and the characters it lists."""

    series: str = ""
    listed: int | None = None
    total: int | None = None
    characters: list[CatalogCharacter] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)


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
            ok, err = validate_catalog_name(name)
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
            if _NOISE_RE.match(line):
                result.noise += 1
                continue
            result.issues.append(ParseIssue(source, line_no, line, "not a series header"))
            continue
        current_series = match.group("series").strip()
        _store_series(
            result,
            CatalogSeries(
                series=current_series,
                listed=int(match.group("listed").replace(",", "")),
                total=int(match.group("total").replace(",", "")),
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


def parse_series_header(line: str) -> CatalogSeries | None:
    """The series + listed/total header, with or without the " - " separator."""
    for pattern in (_SERIES_RE, _SERIES_DM_RE):
        match = pattern.match(line)
        if match:
            return CatalogSeries(
                series=match.group("series").strip(),
                listed=int(match.group("listed").replace(",", "")),
                total=int(match.group("total").replace(",", "")),
            )
    return None


def parse_series_extract(text: str, *, source: str = "") -> SeriesExtract:
    """Parse one `$imartsmi-` DM body into its series and character lines.

    The DM surrounds the character lines with the series header, its aliases,
    per-pool totals and value stats. Only the header and the `#rank - Name ·
    ($pools) - url` lines carry data; every other line is ignored, so an alias
    block or a new Mudae stat line never turns into a parse failure.
    """
    result = ParseResult()
    if source:
        result.sources.append(source)

    text = text.lstrip("\ufeff")
    series = ""
    listed: int | None = None
    total: int | None = None

    for line_no, raw_line in enumerate(text.splitlines(), 1):
        line = _clean_dm_line(raw_line)
        if not line:
            continue
        if line.startswith("#"):
            match = _CHAR_RE.match(line)
            if not match:
                result.issues.append(ParseIssue(source, line_no, line, "not a character line"))
                continue
            name = strip_account_marker(match.group("name").strip())
            ok, err = validate_catalog_name(name)
            if not ok:
                result.issues.append(ParseIssue(source, line_no, line, err or "invalid name"))
                continue
            rank = match.group("rank").replace(",", "").strip()
            if len(rank) > MAX_RANK_LENGTH:
                result.issues.append(ParseIssue(source, line_no, line, "rank too long"))
                continue
            pool, waifu, husbando, anime, game, unknown = parse_pools(match.group("pools"))
            if unknown:
                result.issues.append(
                    ParseIssue(source, line_no, line, f"unknown pool tag(s): {', '.join(unknown)}")
                )
            _store_character(
                result,
                CatalogCharacter(
                    name=name,
                    series=series[:MAX_SERIES_LENGTH],
                    rank=rank,
                    image_url=match.group("url"),
                    pool=pool,
                    is_waifu=waifu,
                    is_husbando=husbando,
                    is_anime=anime,
                    is_game=game,
                ),
            )
            continue

        header = parse_series_header(line)
        if header is not None:
            series = header.series
            listed, total = header.listed, header.total
            _store_series(result, header)
            continue
        # Alias lines, pool totals, AVG/Top-10 stats and any other chrome are
        # deliberately dropped rather than reported.

    return SeriesExtract(
        series=series,
        listed=listed,
        total=total,
        characters=list(result.characters.values()),
        issues=result.issues,
    )


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
            "name": character.name,
            "series": character.series,
            "rank": character.rank,
            "mudae_image_url": character.image_url,
        }
        for key, character in result.characters.items()
    }


def resolve_aliases(entries: dict) -> dict[str, tuple[str, bool]]:
    """Turn a `mudae_aliases.json` mapping into `name_key -> (catalog_key, rename)`.

    `entries` is `{old display name: {"catalog": new display name, "rename": bool}}`.
    The match is keyed the same way everything else is, so the old name's
    spelling in the file does not have to be exact.
    """
    resolved: dict[str, tuple[str, bool]] = {}
    for old_name, value in (entries or {}).items():
        if old_name.startswith("_") or not isinstance(value, dict):
            continue
        catalog_name = value.get("catalog")
        if not catalog_name:
            continue
        resolved[name_key(old_name)] = (name_key(catalog_name), bool(value.get("rename")))
    return resolved


# Round ceilings the coverage table reports against, so "we have everything up
# to N" is checkable rather than asserted.
_COVERAGE_CEILINGS = (100, 250, 500, 1000, 2000, 5000, 10000, 20000, 50000, 100000)


def rank_gaps(result: ParseResult, *, ceilings: list[int] | None = None) -> dict:
    """Where the captured rank numbers are thin.

    Mudae claim ranks are sequential, so a missing integer is a character the
    extract did not capture. Reports the holes between the lowest and highest
    captured rank as contiguous ranges (far more usable than 100k loose numbers),
    plus coverage at round ceilings. Coverage counts ranks 1..ceiling because the
    interesting question is "how complete is the top of the roster", not "how
    many holes are there out to rank 115,000".
    """
    present = {int(c.rank) for c in result.characters.values() if c.rank.isdigit()}
    if not present:
        return {
            "captured": 0,
            "min": None,
            "max": None,
            "missing": 0,
            "missing_pct": 0.0,
            "ranges": [],
            "largest_ranges": [],
            "coverage": [],
            "first_missing": [],
        }

    low = min(present)
    high = max(present)
    missing = [n for n in range(low, high + 1) if n not in present]
    ranges: list[list[int]] = []
    if missing:
        start = prev = missing[0]
        for n in missing[1:]:
            if n == prev + 1:
                prev = n
            else:
                ranges.append([start, prev])
                start = prev = n
        ranges.append([start, prev])

    limits = ceilings or [c for c in _COVERAGE_CEILINGS if c <= high + 1] or [high]
    coverage = []
    for limit in limits:
        captured = sum(1 for n in range(1, limit + 1) if n in present)
        coverage.append(
            {
                "ceiling": limit,
                "captured": captured,
                "missing": limit - captured,
                "pct": round(100 * captured / limit, 1),
            }
        )

    span = high - low + 1
    return {
        "captured": len(present),
        "min": low,
        "max": high,
        "missing": len(missing),
        "missing_pct": round(100 * len(missing) / span, 1),
        "ranges": ranges,
        "largest_ranges": sorted(ranges, key=lambda r: r[1] - r[0], reverse=True)[:15],
        "coverage": coverage,
        "first_missing": missing[:100],
    }


def series_gaps(result: ParseResult, *, limit: int = 50) -> dict:
    """Which captured series are partial, from the "listed/total" headers."""
    rows = [
        {
            "series": s.series,
            "listed": s.listed or 0,
            "total": s.total or 0,
            "missing": max(0, (s.total or 0) - (s.listed or 0)),
        }
        for s in result.series.values()
    ]
    incomplete = sorted(
        (row for row in rows if row["missing"] > 0),
        key=lambda row: row["missing"],
        reverse=True,
    )
    return {
        "series": len(rows),
        "listed": sum(row["listed"] for row in rows),
        "total": sum(row["total"] for row in rows),
        "missing": sum(row["missing"] for row in rows),
        "incomplete": incomplete[:limit],
    }


