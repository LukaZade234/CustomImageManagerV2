"""
On-demand Discord user client for querying Mudae ($im / $ima) via discord.py-self.

Requires DISCORD_USER_TOKEN + DISCORD_CHANNEL_ID. Automating a user account
violates Discord ToS — use a dedicated alt only.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from typing import Any

import discord

import logs

log = logs.get(__name__)

# Official Mudae application user id
_DEFAULT_MUDAE_ID = 432610292342587392

REPLY_TIMEOUT_S = 25.0
ACTION_DELAY_S = 1.0  # pause before Discord actions

# `$imartsmi-` answers by DM, split across as many messages as the list needs.
# The first part arrives after the command is sent; the rest follow immediately,
# so a quiet gap this long means the series list is complete.
DM_IDLE_TIMEOUT_S = 3.0
DM_MAX_WAIT_S = 90.0


class MudaeError(Exception):
    """User-facing Mudae / Discord client error."""


class MudaeCancelled(MudaeError):
    """Raised when a bulk series import is stopped by the user."""


@dataclass
class CharacterInfo:
    name: str
    series: str = ""
    rank: str = ""  # Claim rank number as string (no #)
    image_url: str = ""
    # A card shows the gender beside the series and its pools underneath:
    # "Game & Animanga". Both are on the card for free, so they are parsed and
    # carried through to the character page rather than thrown away.
    is_female: bool = False
    is_male: bool = False
    pools: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CandidateMatch:
    name: str
    series: str = ""

    @property
    def label(self) -> str:
        if self.series:
            return f"{self.name} - {self.series}"
        return self.name

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "series": self.series, "label": self.label}


@dataclass
class LookupResult:
    """Result of $im: a single character card, or a list of candidate names."""

    type: str  # 'character' | 'candidates'
    character: CharacterInfo | None = None
    candidates: list[str] = field(default_factory=list)
    candidate_matches: list[CandidateMatch] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type}
        if self.character:
            d["character"] = self.character.to_dict()
        if self.candidate_matches:
            d["candidate_matches"] = [m.to_dict() for m in self.candidate_matches]
            d["candidates"] = [m.name for m in self.candidate_matches]
        elif self.candidates:
            d["candidates"] = self.candidates
        return d


_lock = threading.Lock()
_series_cancel = threading.Event()


def is_series_cancelled() -> bool:
    return _series_cancel.is_set()


def _raise_if_series_cancelled() -> None:
    if is_series_cancelled():
        raise MudaeCancelled("Series import cancelled by user")


async def _cancellable_sleep(seconds: float) -> None:
    if seconds <= 0:
        return
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _raise_if_series_cancelled()
        await asyncio.sleep(min(0.25, deadline - time.monotonic()))


def _log_mudae_error(context: str, exc: Exception) -> None:
    log.warning("mudae.error", context=context, error=f"{type(exc).__name__}: {exc}")


def _token() -> str:
    return (os.environ.get("DISCORD_USER_TOKEN") or "").strip()


def _channel_id() -> int:
    raw = (os.environ.get("DISCORD_CHANNEL_ID") or "").strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError as e:
        _log_mudae_error("invalid DISCORD_CHANNEL_ID", e)
        raise MudaeError("Invalid Discord channel setting. See DEPLOY.md.") from e


def _mudae_id() -> int:
    raw = (os.environ.get("MUDAE_BOT_USER_ID") or "").strip()
    if not raw:
        return _DEFAULT_MUDAE_ID
    try:
        return int(raw)
    except ValueError as e:
        _log_mudae_error("invalid MUDAE_BOT_USER_ID", e)
        raise MudaeError("Invalid Mudae bot setting. See DEPLOY.md.") from e


def configured() -> bool:
    return bool(_token() and _channel_id())


def require_configured() -> None:
    if not _token():
        raise MudaeError("Mudae import is not configured. See DEPLOY.md.")
    if not _channel_id():
        raise MudaeError("Mudae import is not configured. See DEPLOY.md.")


def _strip_md(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\u200b", "")
    t = re.sub(r"<a?:\w+:\d+>", "", t)
    t = re.sub(r"\|\|(.+?)\|\|", r"\1", t)
    t = re.sub(r"[*_~`]+", "", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _parse_claim_rank(text: str) -> str:
    if not text:
        return ""
    cleaned = _strip_md(text)
    patterns = [
        r"Claims?\s*[:#]?\s*#?\s*([\d,]+)",
        r"#\s*([\d,]+)\s*(?:·|•|\||/)?\s*Claims?",
        r"Claim\s*rank\s*[:#]?\s*#?\s*([\d,]+)",
    ]
    for pat in patterns:
        m = re.search(pat, cleaned, re.IGNORECASE)
        if m:
            return m.group(1).replace(",", "")
    return ""


# The gender sits beside the series. Mudae sends it as a custom emoji, which
# `_strip_md` removes, so gender is read from the raw line; captures that render
# it as the shortcode (`:female:`) or the Unicode sign are accepted too.
_FEMALE_RE = re.compile(r":female:|<a?:female:\d+>|♀", re.IGNORECASE)
_MALE_RE = re.compile(r":male:|<a?:male:\d+>|♂", re.IGNORECASE)

# Trailing gender tokens to strip off the series once the emoji/form is removed.
_GENDER_SUFFIX_RE = re.compile(
    r"\s*(?::female:|:male:|<a?:female:\d+>|<a?:male:\d+>|female|male|girl|boy|♀|♂)\s*$",
    re.IGNORECASE,
)


def _parse_gender(description: str) -> tuple[bool, bool]:
    """(is_female, is_male) from a card. Both can be true; neither may be."""
    text = description or ""
    return bool(_FEMALE_RE.search(text)), bool(_MALE_RE.search(text))


def _parse_pools(description: str) -> str:
    """The pool list a card shows under the series, e.g. "Game & Animanga".

    It arrives as `<pools> · <kakera>`, sometimes with "roulette" in the label
    ("Animanga roulette · 27"). Only the label before the separator is kept.
    """
    for raw in (description or "").splitlines():
        line = _strip_md(raw)
        if not line:
            continue
        m = re.match(r"^(?P<label>.+?)\s*[·•]\s*\d", line)
        if m:
            label = m.group("label").strip()
            if label:
                return label[:120]
    return ""


def _strip_gender_suffix(line: str) -> str:
    previous = None
    while previous != line:
        previous = line
        line = _GENDER_SUFFIX_RE.sub("", line).strip()
    return line


def _series_from_description(description: str) -> str:
    if not description:
        return ""
    skip = re.compile(
        r"^(claims?|likes?|kakera|gender|keys?|roulette|owned|belongs|custom)",
        re.IGNORECASE,
    )
    for raw in description.splitlines():
        line = _strip_md(raw)
        if not line:
            continue
        if skip.match(line):
            continue
        if re.match(r"^#?\d", line):
            continue
        if "claims" in line.lower() and "#" in line:
            continue
        line = re.split(r"\s*[·•|]\s*", line)[0].strip()
        line = _strip_gender_suffix(line)
        if line:
            return line[:300]
    return ""


def _embed_image_url(embed: discord.Embed) -> str:
    if embed.image and embed.image.url:
        return str(embed.image.url)
    if embed.thumbnail and embed.thumbnail.url:
        return str(embed.thumbnail.url)
    return ""


def _character_name_from_embed(embed: discord.Embed) -> str:
    if embed.author and embed.author.name:
        return _strip_md(embed.author.name)
    if embed.title:
        return _strip_md(embed.title)
    return ""


def _im_embed_text_lines(embed: discord.Embed) -> list[str]:
    lines: list[str] = []
    if embed.title:
        lines.append(embed.title)
    if embed.description:
        lines.extend(embed.description.splitlines())
    for field in getattr(embed, "fields", []) or []:
        value = getattr(field, "value", None)
        if value:
            lines.extend(str(value).splitlines())
    return lines


def _is_im_match_header(line: str) -> bool:
    return bool(re.match(r"^\d+\s+matches?\s*:?\s*$", line.strip(), re.I))


def _is_ima_series_count_suffix(text: str) -> bool:
    """Mudae series disambiguation suffix, e.g. 44 or 804 (bundle)."""
    return bool(re.match(r"^\d+(?:\s*\(bundle\))?$", (text or "").strip(), re.I))


def _line_looks_like_ima_series_option(line: str) -> bool:
    if " - " not in line or _is_im_match_header(line):
        return False
    _, _, right = line.partition(" - ")
    return _is_ima_series_count_suffix(right.strip())


def _split_im_candidate_line(line: str) -> tuple[str, str]:
    cleaned = _strip_md(line).strip()
    if " - " in cleaned:
        name, _, series = cleaned.partition(" - ")
        return name.strip(), series.strip()
    return cleaned, ""


def im_lookup_name(text: str) -> str:
    """Name to pass to $im (strip series suffix from Mudae list entries)."""
    name, _ = _split_im_candidate_line(text)
    return name.strip()


def _is_im_list_embed(embed: discord.Embed) -> bool:
    lines = [_strip_md(x) for x in _im_embed_text_lines(embed) if _strip_md(x)]
    if not lines:
        return False
    if any(_is_im_match_header(l) for l in lines[:3]):
        return True
    dash_lines = sum(
        1
        for l in lines
        if " - " in l and not _is_im_match_header(l) and not re.search(r"\bpage\b", l, re.I)
    )
    return dash_lines >= 2


def _parse_im_candidate_matches(embed: discord.Embed) -> list[CandidateMatch]:
    matches: list[CandidateMatch] = []
    seen: set[str] = set()
    for raw in _im_embed_text_lines(embed):
        line = _strip_md(raw)
        if not line or _is_im_match_header(line):
            continue
        if re.search(r"\bpage\b|\bresults?\b", line, re.IGNORECASE) and len(line) < 40:
            if not re.search(r"[a-zA-Z]{3,}.+[a-zA-Z]{3,}", line):
                continue
        line = re.sub(r"^\d+[\).\:\-]\s*", "", line)
        line = re.sub(r"^[-•*]\s*", "", line).strip()
        if len(line) < 2 or len(line) > 200:
            continue
        if line.lower() in ("n/a", "none"):
            continue
        name, series = _split_im_candidate_line(line)
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        matches.append(CandidateMatch(name=name, series=series))
    return matches


def _is_character_card(embed: discord.Embed) -> bool:
    return bool(_embed_image_url(embed) and _character_name_from_embed(embed))


def parse_im_embed(embed: discord.Embed) -> LookupResult:
    desc = embed.description or ""
    footer = embed.footer.text if embed.footer else ""
    full_text = "\n".join(filter(None, [embed.title or "", desc, footer]))

    if _is_im_list_embed(embed):
        matches = _parse_im_candidate_matches(embed)
        if not matches:
            raise MudaeError("Could not parse Mudae character list")
        return LookupResult(
            type="candidates",
            candidate_matches=matches,
        )

    if _is_character_card(embed):
        is_female, is_male = _parse_gender(desc)
        return LookupResult(
            type="character",
            character=CharacterInfo(
                name=_character_name_from_embed(embed),
                series=_series_from_description(desc),
                rank=_parse_claim_rank(full_text),
                image_url=_embed_image_url(embed),
                is_female=is_female,
                is_male=is_male,
                pools=_parse_pools(desc),
            ),
        )

    candidates: list[str] = []
    for raw in _im_embed_text_lines(embed):
        line = _strip_md(raw)
        if not line or _is_im_match_header(line):
            continue
        if (
            re.search(r"\bpage\b|\bresults?\b|\bcharacters?\b", line, re.IGNORECASE)
            and len(line) < 40
        ):
            if not re.search(r"[a-zA-Z]{3,}.+[a-zA-Z]{3,}", line):
                continue
        line = re.sub(r"^\d+[\).\:\-]\s*", "", line)
        line = re.sub(r"^[-•*]\s*", "", line).strip()
        if len(line) < 1 or len(line) > 200:
            continue
        if line.lower() in ("n/a", "none"):
            continue
        name, _ = _split_im_candidate_line(line)
        if name:
            candidates.append(name)

    if not candidates and embed.title:
        t = _strip_md(embed.title)
        if t and not re.search(r"results?|search|matches?", t, re.IGNORECASE):
            candidates.append(im_lookup_name(t))

    seen: set[str] = set()
    uniq: list[str] = []
    for c in candidates:
        key = c.casefold()
        if key in seen:
            continue
        seen.add(key)
        uniq.append(c)

    if not uniq:
        raise MudaeError("Could not parse Mudae $im reply (no character card or name list)")
    return LookupResult(
        type="candidates",
        candidates=uniq,
        candidate_matches=[CandidateMatch(name=n) for n in uniq],
    )


class _TextEmbed:
    """Minimal embed-like object for plain-text Mudae replies."""

    def __init__(self, text: str) -> None:
        self.title = None
        self.description = text
        self.footer = None
        self.author = None
        self.image = None
        self.thumbnail = None
        self.fields: list = []


def parse_im_message(msg: discord.Message) -> LookupResult:
    if msg.embeds:
        return parse_im_embed(msg.embeds[0])
    text = (msg.content or "").strip()
    if not text:
        raise MudaeError("Mudae reply had no content")
    return parse_im_embed(_TextEmbed(text))


def _dm_body(msg: discord.Message) -> str:
    """The text of one DM part: message content, else the first embed's body."""
    text = (msg.content or "").strip()
    if text:
        return text
    if msg.embeds:
        embed = msg.embeds[0]
        parts = [embed.title or ""]
        if embed.description:
            parts.append(embed.description)
        for field in getattr(embed, "fields", []) or []:
            value = getattr(field, "value", None)
            if value:
                parts.append(str(value))
        return "\n".join(part for part in parts if part).strip()
    return ""


def _ima_text_ready(text: str) -> bool:
    text = (text or "").strip()
    if not text:
        return False
    if re.search(r"\d+\s+matches?\b", text, re.I):
        return True
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return len(lines) >= 2


def _is_blank_ima_line(raw: str) -> bool:
    if raw is None:
        return True
    if not raw.strip():
        return True
    return not _strip_md(raw)


def _is_obvious_character_name(line: str) -> bool:
    if "(" in line and ")" in line:
        return True
    if re.search(r"-\d", line):
        return True
    s = line.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,7}", s):
        if re.fullmatch(r"[A-Z][a-z]+", s) and len(s) >= 5:
            return False
        return False
    if " " not in s and len(s) >= 5 and re.match(r"^[A-Za-z]", s):
        return True
    if " " in s:
        words = [w for w in s.split() if w]
        if words and any(len(w) > 5 for w in words):
            return True
    return False


def _line_is_short_multiword_alias(line: str) -> bool:
    """Multi-word series aliases like Ming Chao (not Character One)."""
    if "(" in line and ")" in line:
        return False
    if " " not in line:
        return False
    words = [w for w in line.split() if w]
    return bool(words) and all(len(w) <= 5 for w in words)


def _is_ima_noise_line(line: str, *, series_hint: str = "", series_label: str = "") -> bool:
    if not line:
        return True
    if _is_im_match_header(line):
        return True
    if re.search(r"\bpage\s*\d|\bcharacters?\b\s*:?\s*$", line, re.IGNORECASE) and len(line) < 50:
        return True
    if re.search(r"\b\d+\s*/\s*\d+\b", line):
        return True
    if "/" in line or "\\" in line:
        return True
    lc = line.casefold()
    for hint in (series_hint, series_label, clean_series_label(series_label)):
        h = (hint or "").strip().casefold()
        if not h:
            continue
        if lc == h:
            return True
        if lc.startswith(h) and re.search(r"\b\d+\s*/\s*\d+\b", line):
            return True
    return False


def _line_is_series_alias(line: str, *, series_hint: str = "", series_label: str = "") -> bool:
    """Alternate series title on $ima page 1 — not a character name."""
    line = line.strip()
    if not line:
        return False
    if "(" in line and ")" in line:
        return False
    lc = line.casefold()
    for hint in (series_hint, series_label, clean_series_label(series_label)):
        h = (hint or "").strip().casefold()
        if h and lc == h:
            return True
    # CJK-only titles (e.g. 鸣潮)
    if not re.search(r"[a-zA-Z]", line) and re.search(r"[\u4e00-\u9fff]", line):
        return True
    # Short latin acronym (e.g. WuWa) — not normal names like Aalto or Baizhi
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9]{1,7}", line):
        if re.fullmatch(r"[A-Z][a-z]+", line) and len(line) >= 5:
            return False
        return True
    return False


def _drop_leading_series_aliases(
    lines: list[str],
    *,
    series_hint: str = "",
    series_label: str = "",
) -> list[str]:
    """First page without a blank gap: skip alias block before character names."""
    i = 0
    while i < len(lines):
        line = (lines[i] or "").strip()
        if not line:
            i += 1
            continue
        if _is_ima_noise_line(line, series_hint=series_hint, series_label=series_label):
            i += 1
            continue
        if _line_is_series_alias(line, series_hint=series_hint, series_label=series_label):
            i += 1
            continue
        if _is_obvious_character_name(line):
            break
        if _line_is_short_multiword_alias(line):
            i += 1
            continue
        break
    return lines[i:]


def _ima_character_source_lines(
    desc: str,
    *,
    first_page: bool,
    series_hint: str = "",
    series_label: str = "",
) -> list[str]:
    """Lines from $ima embed description that may contain character names."""
    raw_desc = desc or ""
    if not first_page:
        return [_strip_md(raw) for raw in raw_desc.splitlines()]

    # Paragraph break between aliases and characters
    if re.search(r"\n\s*\n", raw_desc):
        _prefix, suffix = re.split(r"\n\s*\n", raw_desc, maxsplit=1)
        return [_strip_md(raw) for raw in suffix.splitlines()]

    raw_lines = raw_desc.splitlines()
    gap_idx = next((i for i, raw in enumerate(raw_lines) if _is_blank_ima_line(raw)), None)
    if gap_idx is not None:
        return [_strip_md(raw) for raw in raw_lines[gap_idx + 1 :]]

    stripped = [_strip_md(raw) for raw in raw_lines]
    return _drop_leading_series_aliases(
        stripped,
        series_hint=series_hint,
        series_label=series_label,
    )


def parse_ima_names(
    embed: discord.Embed,
    *,
    series_hint: str = "",
    series_label: str = "",
    first_page: bool = True,
) -> list[str]:
    desc = embed.description or ""
    names: list[str] = []
    for raw in _ima_character_source_lines(
        desc,
        first_page=first_page,
        series_hint=series_hint,
        series_label=series_label,
    ):
        line = raw.strip()
        if not line:
            continue
        if _is_ima_noise_line(line, series_hint=series_hint, series_label=series_label):
            continue
        if first_page and _line_is_series_alias(
            line, series_hint=series_hint, series_label=series_label
        ):
            continue
        if first_page and _line_is_short_multiword_alias(line):
            continue
        line = re.sub(r"^\d+[\).\:\-]\s*", "", line)
        line = re.sub(r"^[-•*]\s*", "", line).strip()
        if " - " in line:
            left, right = line.split(" - ", 1)
            if len(right) < 40:
                line = left.strip()
        if 1 <= len(line) <= 200:
            names.append(line)

    seen: set[str] = set()
    out: list[str] = []
    for n in names:
        k = n.casefold()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out


def _parse_ima_series_candidates(embed: discord.Embed) -> list[CandidateMatch]:
    """Parse ambiguous $ima series list (multiple series names, not characters)."""
    matches: list[CandidateMatch] = []
    seen: set[str] = set()
    for raw in _im_embed_text_lines(embed):
        line = _strip_md(raw)
        if not line or _is_im_match_header(line):
            continue
        if re.search(r"\bpage\b", line, re.I) and len(line) < 40:
            continue
        if re.search(r"\d+\s*/\s*\d+", line):
            continue
        line = re.sub(r"^\d+[\).\:\-]\s*", "", line)
        line = re.sub(r"^[-•*]\s*", "", line).strip()
        if len(line) < 2 or len(line) > 200:
            continue
        if line.lower() in ("n/a", "none"):
            continue
        name, extra = _split_im_candidate_line(line)
        if not name:
            continue
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        matches.append(CandidateMatch(name=name, series=extra))
    return matches


def _is_ima_ambiguous_series_embed(embed: discord.Embed) -> bool:
    if _footer_page_info(embed) is not None:
        return False
    if _is_character_card(embed):
        return False
    lines = [_strip_md(x) for x in _im_embed_text_lines(embed) if _strip_md(x)]
    if any(_is_im_match_header(l) for l in lines[:3]):
        return True
    series_option_lines = sum(1 for l in lines if _line_looks_like_ima_series_option(l))
    if series_option_lines >= 2:
        return True
    return len(_parse_ima_series_candidates(embed)) >= 2


def _footer_page_info(embed: discord.Embed) -> tuple[int, int] | None:
    footer = embed.footer.text if embed.footer else ""
    m = re.search(r"(\d+)\s*/\s*(\d+)", footer)
    if m:
        return int(m.group(1)), int(m.group(2))
    for part in (
        embed.description or "",
        embed.title or "",
        _strip_md(embed.author.name if embed.author and embed.author.name else ""),
    ):
        m = re.search(r"(\d+)\s*/\s*(\d+)", part)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def clean_series_label(label: str) -> str:
    """Strip Mudae pagination suffixes like 'Silver Palace 0/8'."""
    s = (label or "").strip()
    cleaned = re.sub(r"\s+\d+\s*/\s*\d+\s*$", "", s).strip()
    return cleaned or s


class _MudaeSession:
    """On-demand discord.py-self connection: connect, query Mudae, disconnect."""

    def __init__(self) -> None:
        require_configured()
        self._client: discord.Client | None = None
        self._channel: discord.TextChannel | discord.Thread | discord.VoiceChannel | None = None
        self._mudae_id = _mudae_id()
        self._channel_id = _channel_id()
        self._ready = asyncio.Event()
        self._pending: asyncio.Future[discord.Message] | None = None
        self._start_task: asyncio.Task | None = None
        self._expect_message_id: int | None = None
        self._reply_not_before: float | None = None
        # `$imartsmi-` collects the series list from DMs, not the channel.
        self._dm_parts: list[str] = []
        self._dm_event: asyncio.Event | None = None
        self._dm_active = False
        self._dm_not_before = 0.0

    def _message_in_target_channel(self, message: discord.Message) -> bool:
        ch = message.channel
        if ch.id == self._channel_id:
            return True
        parent_id = getattr(ch, "parent_id", None)
        return parent_id == self._channel_id

    def _mudae_message_ready(self, message: discord.Message) -> bool:
        if message.embeds:
            return True
        content = (message.content or "").strip()
        if not content:
            return False
        if re.search(r"\d+\s+matches?\b", content, re.I):
            return True
        if " - " in content and len(content) > 10:
            return True
        return False

    async def _poll_recent_mudae_reply(self) -> discord.Message | None:
        if self._channel is None:
            return None
        not_before = self._reply_not_before or (time.time() - 30.0)
        try:
            async for msg in self._channel.history(limit=15):
                if msg.author.id != self._mudae_id:
                    continue
                if not self._message_in_target_channel(msg):
                    continue
                if self._expect_message_id is not None and msg.id != self._expect_message_id:
                    continue
                if msg.created_at.timestamp() < not_before:
                    continue
                if self._mudae_message_ready(msg):
                    log.debug("mudae.reply_polled", message_id=msg.id)
                    return msg
        except Exception as exc:
            log.warning("mudae.history_poll_failed", error=f"{type(exc).__name__}: {exc}")
        return None

    async def _action_pause(self, extra: float = 0.0) -> None:
        await _cancellable_sleep(ACTION_DELAY_S + extra)

    async def _refresh_message(self, msg: discord.Message) -> discord.Message:
        if self._channel is None:
            return msg
        try:
            return await self._channel.fetch_message(msg.id)
        except Exception:
            return msg

    async def __aenter__(self) -> _MudaeSession:
        # discord.py-self 2.1.0 has no Intents — user clients use plain Client().
        client = discord.Client()
        self._client = client

        @client.event
        async def on_ready():
            self._ready.set()

        @client.event
        async def on_message(message: discord.Message):
            await self._maybe_capture(message)
            await self._maybe_capture_dm(message)

        @client.event
        async def on_message_edit(_before: discord.Message, after: discord.Message):
            await self._maybe_capture(after)

        self._start_task = asyncio.create_task(client.start(_token()))
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30.0)
        except TimeoutError as e:
            await self._shutdown()
            raise MudaeError("Timed out connecting to Discord") from e
        except discord.LoginFailure as e:
            await self._shutdown()
            _log_mudae_error("Discord login failed", e)
            raise MudaeError("Could not sign in to Discord. Check your setup in DEPLOY.md.") from e

        channel = client.get_channel(self._channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(self._channel_id)
            except Exception as e:
                await self._shutdown()
                _log_mudae_error(f"could not open channel {self._channel_id}", e)
                raise MudaeError(
                    "Could not access the configured Discord channel. See DEPLOY.md."
                ) from e
        self._channel = channel  # type: ignore[assignment]
        return self

    async def __aexit__(self, *exc) -> None:
        await self._shutdown()

    async def _shutdown(self) -> None:
        client = self._client
        self._client = None
        if client is not None and not client.is_closed():
            await client.close()
        task = self._start_task
        self._start_task = None
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except Exception:
                task.cancel()

    async def _maybe_capture(self, message: discord.Message) -> None:
        if self._pending is None or self._pending.done():
            return
        if message.author.id != self._mudae_id:
            return
        if not self._message_in_target_channel(message):
            return
        if self._expect_message_id is not None and message.id != self._expect_message_id:
            return
        if not self._mudae_message_ready(message):
            return
        log.debug("mudae.reply_captured", message_id=message.id, embeds=len(message.embeds))
        self._pending.set_result(message)

    async def _maybe_capture_dm(self, message: discord.Message) -> None:
        """Collect one part of a `$imartsmi-` DM while a fetch is in flight."""
        if not self._dm_active or self._dm_event is None:
            return
        if message.author.id != self._mudae_id:
            return
        # A DM has no guild; a same-author message in the channel is not it.
        if getattr(message, "guild", None) is not None:
            return
        if message.created_at.timestamp() < self._dm_not_before:
            return
        body = _dm_body(message)
        if not body:
            return
        self._dm_parts.append(body)
        log.debug("mudae.dm_part_captured", message_id=message.id)
        self._dm_event.set()

    async def _next_dm_part(self, timeout: float) -> bool:
        event = self._dm_event
        if event is None:
            return False
        if event.is_set():
            event.clear()
            return True
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError:
            return False
        event.clear()
        return True

    async def fetch_series_extract_dm(self, series: str) -> str:
        """Send `$imartsmi- <series>` and return the concatenated DM reply.

        Mudae answers to the account's DMs and splits a long list across several
        messages. Parts are collected until the header's total is reached or the
        messages stop arriving, whichever comes first.
        """
        if self._channel is None:
            raise MudaeError("Discord channel not available")
        series = (series or "").strip()
        if not series:
            raise MudaeError("Series name is required")
        _raise_if_series_cancelled()

        await self._action_pause()
        self._dm_parts = []
        self._dm_event = asyncio.Event()
        self._dm_active = True
        self._dm_not_before = time.time() - 1.0
        try:
            await self._channel.send(f"$imartsmi- {series}")
            return await self._collect_series_dm()
        finally:
            self._dm_active = False
            self._dm_event = None

    async def _collect_series_dm(self) -> str:
        if not await self._next_dm_part(REPLY_TIMEOUT_S):
            raise MudaeError("Mudae did not send the series list in a DM")

        deadline = time.monotonic() + DM_MAX_WAIT_S
        while time.monotonic() < deadline:
            _raise_if_series_cancelled()
            text = "\n".join(self._dm_parts)
            # Local import keeps this module free of the catalog parser except
            # for the completeness check it needs here.
            import catalog_import

            parsed = catalog_import.parse_series_extract(text)
            if parsed.total and len(parsed.characters) >= parsed.total:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if not await self._next_dm_part(min(DM_IDLE_TIMEOUT_S, remaining)):
                break

        text = "\n".join(self._dm_parts)
        if not text.strip():
            raise MudaeError("Mudae did not send the series list in a DM")
        return text

    async def _wait_for_pending_reply(self, timeout: float = REPLY_TIMEOUT_S) -> discord.Message:
        if self._pending is None:
            raise MudaeError("Internal error waiting for Mudae reply")
        deadline = time.monotonic() + timeout
        last_poll = 0.0
        try:
            while True:
                _raise_if_series_cancelled()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    polled = await self._poll_recent_mudae_reply()
                    if polled is not None:
                        return polled
                    raise MudaeError("Timed out waiting for Mudae reply")
                if self._pending.done():
                    return self._pending.result()
                now = time.monotonic()
                if now - last_poll >= 0.5:
                    last_poll = now
                    polled = await self._poll_recent_mudae_reply()
                    if polled is not None and not self._pending.done():
                        self._pending.set_result(polled)
                    if self._pending.done():
                        return self._pending.result()
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(self._pending), timeout=min(0.25, remaining)
                    )
                except TimeoutError:
                    if self._pending.done():
                        return self._pending.result()
                    continue
        except asyncio.CancelledError:
            raise MudaeCancelled("Series import cancelled by user") from None

    async def send_and_wait(
        self,
        content: str,
        timeout: float = REPLY_TIMEOUT_S,
        *,
        pause_before: bool = True,
    ) -> discord.Message:
        if self._channel is None:
            raise MudaeError("Discord channel not available")
        _raise_if_series_cancelled()
        if pause_before:
            await self._action_pause()
        loop = asyncio.get_running_loop()
        self._pending = loop.create_future()
        self._reply_not_before = time.time() - 2.0
        try:
            await self._channel.send(content)
            msg = await self._wait_for_pending_reply(timeout=timeout)
            _raise_if_series_cancelled()
            return msg
        finally:
            self._pending = None
            self._reply_not_before = None

    async def _ensure_embed_ready(self, msg: discord.Message) -> discord.Message:
        """Wait briefly for Mudae to finish populating list/card embeds or plain-text body."""
        deadline = time.monotonic() + 6.0
        last = msg
        while time.monotonic() < deadline:
            msg = await self._refresh_message(msg)
            last = msg
            if msg.embeds:
                embed = msg.embeds[0]
                if _is_im_list_embed(embed):
                    if _parse_im_candidate_matches(embed):
                        return msg
                elif _is_character_card(embed):
                    return msg
                elif _is_ima_ambiguous_series_embed(embed):
                    if _parse_ima_series_candidates(embed):
                        return msg
                elif parse_ima_names(embed, series_hint="", series_label="", first_page=True):
                    return msg
            content = (msg.content or "").strip()
            if content and (self._mudae_message_ready(msg) or _ima_text_ready(content)):
                return msg
            await asyncio.sleep(0.35)
        return last

    async def lookup_im(self, name: str, *, pause_before: bool = True) -> LookupResult:
        name = (name or "").strip()
        if not name:
            raise MudaeError("Character name is required")
        _raise_if_series_cancelled()
        msg = await self.send_and_wait(f"$im {name}", pause_before=pause_before)
        msg = await self._ensure_embed_ready(msg)
        return parse_im_message(msg)


def _run_async(coro):
    return asyncio.run(coro)


def with_discord_lock(fn: Callable[[], Any]) -> Any:
    require_configured()
    acquired = _lock.acquire(blocking=False)
    if not acquired:
        raise MudaeError("Another Mudae request is already in progress; try again shortly")
    try:
        return fn()
    finally:
        _lock.release()


def lookup_character(name: str) -> LookupResult:
    def _do():
        async def _inner():
            async with _MudaeSession() as session:
                return await session.lookup_im(name)

        return _run_async(_inner())

    return with_discord_lock(_do)


def fetch_series_extract(series: str) -> str:
    """$imartsmi- a series and return the raw DM body for the caller to parse."""

    def _do():
        async def _inner():
            async with _MudaeSession() as session:
                return await session.fetch_series_extract_dm(series)

        return _run_async(_inner())

    return with_discord_lock(_do)


def lookup_character_exact(name: str) -> CharacterInfo:
    result = lookup_character(name)
    if result.type == "character" and result.character:
        return result.character
    cands = result.candidate_matches or [CandidateMatch(name=n) for n in (result.candidates or [])]
    labels = [c.label for c in cands[:20]]
    raise MudaeError(
        "Ambiguous character name; pick one: " + ", ".join(labels)
        if labels
        else "Character not found in Mudae"
    )

