"""
On-demand Discord user client for querying Mudae ($im / $ima) via discord.py-self.

Requires DISCORD_USER_TOKEN + DISCORD_CHANNEL_ID. Automating a user account
violates Discord ToS — use a dedicated alt only.
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Optional, Union

import discord
from discord.components import Button

# Official Mudae application user id
_DEFAULT_MUDAE_ID = 432610292342587392

REPLY_TIMEOUT_S = 25.0
ACTION_DELAY_S = 1.0  # pause before Discord actions outside bulk $im pacing
POST_IMA_TO_IM_DELAY_S = 1.0  # gap after $ima before the first $im
IM_INTERVAL_S = 1.0  # target min gap between $im sends when lookup + persist succeed
IM_RETRY_DELAY_S = 2.5  # longer wait before retrying a failed lookup or persist
IMA_PAGE_DELAY_S = 2.2
MAX_IMA_PAGES = 40
CHARACTER_LOOKUP_RETRIES = 2  # 3 attempts total per character
IMA_REACTION_WAIT_S = 10.0


class MudaeError(Exception):
    """User-facing Mudae / Discord client error."""


class MudaeCancelled(MudaeError):
    """Raised when a bulk series import is stopped by the user."""


class MudaeAmbiguousSeries(MudaeError):
    """$ima returned multiple series options instead of a character list."""

    def __init__(self, query: str, candidate_matches: list['CandidateMatch']) -> None:
        self.query = query
        self.candidate_matches = candidate_matches
        labels = [m.label for m in candidate_matches[:20]]
        suffix = f' (+{len(candidate_matches) - 20} more)' if len(candidate_matches) > 20 else ''
        super().__init__('Ambiguous series name; pick one: ' + ', '.join(labels) + suffix)

    def to_dict(self) -> dict[str, Any]:
        return {
            'type': 'candidates',
            'query': self.query,
            'error': str(self),
            'candidate_matches': [m.to_dict() for m in self.candidate_matches],
            'candidates': [m.name for m in self.candidate_matches],
        }


@dataclass
class CharacterInfo:
    name: str
    series: str = ''
    rank: str = ''  # Claim rank number as string (no #)
    image_url: str = ''

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass
class CandidateMatch:
    name: str
    series: str = ''

    @property
    def label(self) -> str:
        if self.series:
            return f'{self.name} - {self.series}'
        return self.name

    def to_dict(self) -> dict[str, str]:
        return {'name': self.name, 'series': self.series, 'label': self.label}


@dataclass
class LookupResult:
    """Result of $im: a single character card, or a list of candidate names."""
    type: str  # 'character' | 'candidates'
    character: Optional[CharacterInfo] = None
    candidates: list[str] = field(default_factory=list)
    candidate_matches: list[CandidateMatch] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {'type': self.type}
        if self.character:
            d['character'] = self.character.to_dict()
        if self.candidate_matches:
            d['candidate_matches'] = [m.to_dict() for m in self.candidate_matches]
            d['candidates'] = [m.name for m in self.candidate_matches]
        elif self.candidates:
            d['candidates'] = self.candidates
        return d


@dataclass
class SeriesLookupResult:
    """Result of $ima: a series character list, or ambiguous series names."""
    type: str  # 'series' | 'candidates'
    series_label: str = ''
    query: str = ''
    candidate_matches: list[CandidateMatch] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {'type': self.type, 'query': self.query}
        if self.type == 'series':
            d['series_label'] = self.series_label
        if self.candidate_matches:
            d['candidate_matches'] = [m.to_dict() for m in self.candidate_matches]
            d['candidates'] = [m.name for m in self.candidate_matches]
        return d


_lock = threading.Lock()
_series_cancel = threading.Event()


def clear_series_cancel() -> None:
    _series_cancel.clear()


def request_series_cancel() -> None:
    _series_cancel.set()


def is_series_cancelled() -> bool:
    return _series_cancel.is_set()


def _raise_if_series_cancelled() -> None:
    if is_series_cancelled():
        raise MudaeCancelled('Series import cancelled by user')


async def _cancellable_sleep(seconds: float) -> None:
    if seconds <= 0:
        return
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        _raise_if_series_cancelled()
        await asyncio.sleep(min(0.25, deadline - time.monotonic()))


class _ImPacer:
    """Enforce a minimum interval between successful $im + persist cycles."""

    __slots__ = ('interval', '_last_done')

    def __init__(self, interval: float = IM_INTERVAL_S) -> None:
        self.interval = interval
        self._last_done: Optional[float] = None

    async def before_next(self) -> None:
        if self._last_done is None:
            return
        remaining = self.interval - (time.monotonic() - self._last_done)
        if remaining > 0:
            await _cancellable_sleep(remaining)

    def mark_done(self) -> None:
        self._last_done = time.monotonic()


# Unicode arrows the bot may have added by mistake — not Mudae's nav buttons.
_NAV_ARROW_EMOJI = frozenset({'➡️', '▶️', '▶', '⏩', '⬅️', '◀️', '◀', '⏪'})


def _mudae_nav_buttons(msg: discord.Message) -> list[Button]:
    """Mudae $ima nav as message component buttons (1st = prev, 2nd = next)."""
    out: list[Button] = []
    for row in getattr(msg, 'components', []) or []:
        for child in getattr(row, 'children', []) or []:
            if isinstance(child, Button):
                out.append(child)
    return out


def _mudae_nav_reactions(msg: discord.Message) -> list:
    """Mudae $ima nav buttons are custom emojis on the message (1st = prev, 2nd = next)."""
    out: list = []
    for reaction in msg.reactions:
        if isinstance(reaction.emoji, str):
            continue
        if not reaction.is_custom_emoji():
            continue
        emoji_str = str(reaction.emoji)
        if emoji_str in _NAV_ARROW_EMOJI:
            continue
        out.append(reaction)

    out.sort(key=lambda r: int(getattr(r.emoji, 'id', 0) or 0))
    return out


def _mudae_nav_ready(msg: discord.Message, min_count: int = 2) -> bool:
    return len(_mudae_nav_buttons(msg)) >= min_count or len(_mudae_nav_reactions(msg)) >= min_count


def _embed_marker(embed: discord.Embed) -> str:
    return (embed.description or '') + '|' + (embed.footer.text if embed.footer else '')


def _ima_embed_changed(msg: discord.Message, prev_marker: str, prev_page_idx: int) -> bool:
    if not msg.embeds:
        return False
    embed = msg.embeds[0]
    if _embed_marker(embed) != prev_marker:
        return True
    page = _footer_page_info(embed)
    return page is not None and page[0] != prev_page_idx


def _log_mudae_error(context: str, exc: Exception) -> None:
    print(f'[MUDAE] {context}: {type(exc).__name__}: {exc}', flush=True)


def _token() -> str:
    return (os.environ.get('DISCORD_USER_TOKEN') or '').strip()


def _channel_id() -> int:
    raw = (os.environ.get('DISCORD_CHANNEL_ID') or '').strip()
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError as e:
        _log_mudae_error('invalid DISCORD_CHANNEL_ID', e)
        raise MudaeError('Invalid Discord channel setting. See DEPLOY.md.') from e


def _mudae_id() -> int:
    raw = (os.environ.get('MUDAE_BOT_USER_ID') or '').strip()
    if not raw:
        return _DEFAULT_MUDAE_ID
    try:
        return int(raw)
    except ValueError as e:
        _log_mudae_error('invalid MUDAE_BOT_USER_ID', e)
        raise MudaeError('Invalid Mudae bot setting. See DEPLOY.md.') from e


def configured() -> bool:
    return bool(_token() and _channel_id())


def require_configured() -> None:
    if not _token():
        raise MudaeError('Mudae import is not configured. See DEPLOY.md.')
    if not _channel_id():
        raise MudaeError('Mudae import is not configured. See DEPLOY.md.')


def _strip_md(text: str) -> str:
    if not text:
        return ''
    t = text.replace('\u200b', '')
    t = re.sub(r'<a?:\w+:\d+>', '', t)
    t = re.sub(r'\|\|(.+?)\|\|', r'\1', t)
    t = re.sub(r'[*_~`]+', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.strip()


def _parse_claim_rank(text: str) -> str:
    if not text:
        return ''
    cleaned = _strip_md(text)
    patterns = [
        r'Claims?\s*[:#]?\s*#?\s*([\d,]+)',
        r'#\s*([\d,]+)\s*(?:·|•|\||/)?\s*Claims?',
        r'Claim\s*rank\s*[:#]?\s*#?\s*([\d,]+)',
    ]
    for pat in patterns:
        m = re.search(pat, cleaned, re.IGNORECASE)
        if m:
            return m.group(1).replace(',', '')
    return ''


def _series_from_description(description: str) -> str:
    if not description:
        return ''
    skip = re.compile(
        r'^(claims?|likes?|kakera|gender|keys?|roulette|owned|belongs|custom)',
        re.IGNORECASE,
    )
    for raw in description.splitlines():
        line = _strip_md(raw)
        if not line:
            continue
        if skip.match(line):
            continue
        if re.match(r'^#?\d', line):
            continue
        if 'claims' in line.lower() and '#' in line:
            continue
        line = re.split(r'\s*[·•|]\s*', line)[0].strip()
        line = re.sub(r'\s+(female|male|girl|boy)\s*$', '', line, flags=re.IGNORECASE).strip()
        if line:
            return line[:300]
    return ''


def _embed_image_url(embed: discord.Embed) -> str:
    if embed.image and embed.image.url:
        return str(embed.image.url)
    if embed.thumbnail and embed.thumbnail.url:
        return str(embed.thumbnail.url)
    return ''


def _character_name_from_embed(embed: discord.Embed) -> str:
    if embed.author and embed.author.name:
        return _strip_md(embed.author.name)
    if embed.title:
        return _strip_md(embed.title)
    return ''


def _im_embed_text_lines(embed: discord.Embed) -> list[str]:
    lines: list[str] = []
    if embed.title:
        lines.append(embed.title)
    if embed.description:
        lines.extend(embed.description.splitlines())
    for field in getattr(embed, 'fields', []) or []:
        value = getattr(field, 'value', None)
        if value:
            lines.extend(str(value).splitlines())
    return lines


def _is_im_match_header(line: str) -> bool:
    return bool(re.match(r'^\d+\s+matches?\s*:?\s*$', line.strip(), re.I))


def _is_ima_series_count_suffix(text: str) -> bool:
    """Mudae series disambiguation suffix, e.g. 44 or 804 (bundle)."""
    return bool(re.match(r'^\d+(?:\s*\(bundle\))?$', (text or '').strip(), re.I))


def _line_looks_like_ima_series_option(line: str) -> bool:
    if ' - ' not in line or _is_im_match_header(line):
        return False
    _, _, right = line.partition(' - ')
    return _is_ima_series_count_suffix(right.strip())


def _split_im_candidate_line(line: str) -> tuple[str, str]:
    cleaned = _strip_md(line).strip()
    if ' - ' in cleaned:
        name, _, series = cleaned.partition(' - ')
        return name.strip(), series.strip()
    return cleaned, ''


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
        1 for l in lines
        if ' - ' in l and not _is_im_match_header(l) and not re.search(r'\bpage\b', l, re.I)
    )
    return dash_lines >= 2


def _parse_im_candidate_matches(embed: discord.Embed) -> list[CandidateMatch]:
    matches: list[CandidateMatch] = []
    seen: set[str] = set()
    for raw in _im_embed_text_lines(embed):
        line = _strip_md(raw)
        if not line or _is_im_match_header(line):
            continue
        if re.search(r'\bpage\b|\bresults?\b', line, re.IGNORECASE) and len(line) < 40:
            if not re.search(r'[a-zA-Z]{3,}.+[a-zA-Z]{3,}', line):
                continue
        line = re.sub(r'^\d+[\).\:\-]\s*', '', line)
        line = re.sub(r'^[-•*]\s*', '', line).strip()
        if len(line) < 2 or len(line) > 200:
            continue
        if line.lower() in ('n/a', 'none'):
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
    desc = embed.description or ''
    footer = embed.footer.text if embed.footer else ''
    full_text = '\n'.join(filter(None, [embed.title or '', desc, footer]))

    if _is_im_list_embed(embed):
        matches = _parse_im_candidate_matches(embed)
        if not matches:
            raise MudaeError('Could not parse Mudae character list')
        return LookupResult(
            type='candidates',
            candidate_matches=matches,
        )

    if _is_character_card(embed):
        return LookupResult(
            type='character',
            character=CharacterInfo(
                name=_character_name_from_embed(embed),
                series=_series_from_description(desc),
                rank=_parse_claim_rank(full_text),
                image_url=_embed_image_url(embed),
            ),
        )

    candidates: list[str] = []
    for raw in _im_embed_text_lines(embed):
        line = _strip_md(raw)
        if not line or _is_im_match_header(line):
            continue
        if re.search(r'\bpage\b|\bresults?\b|\bcharacters?\b', line, re.IGNORECASE) and len(line) < 40:
            if not re.search(r'[a-zA-Z]{3,}.+[a-zA-Z]{3,}', line):
                continue
        line = re.sub(r'^\d+[\).\:\-]\s*', '', line)
        line = re.sub(r'^[-•*]\s*', '', line).strip()
        if len(line) < 1 or len(line) > 200:
            continue
        if line.lower() in ('n/a', 'none'):
            continue
        name, _ = _split_im_candidate_line(line)
        if name:
            candidates.append(name)

    if not candidates and embed.title:
        t = _strip_md(embed.title)
        if t and not re.search(r'results?|search|matches?', t, re.IGNORECASE):
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
        raise MudaeError('Could not parse Mudae $im reply (no character card or name list)')
    return LookupResult(
        type='candidates',
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
    text = (msg.content or '').strip()
    if not text:
        raise MudaeError('Mudae reply had no content')
    return parse_im_embed(_TextEmbed(text))


def _ima_reply_embed(msg: discord.Message, fallback: str):
    if msg.embeds:
        return msg.embeds[0]
    text = (msg.content or '').strip()
    if not text:
        raise MudaeError('Mudae $ima reply had no content')
    return _TextEmbed(text)


def _ima_text_ready(text: str) -> bool:
    text = (text or '').strip()
    if not text:
        return False
    if re.search(r'\d+\s+matches?\b', text, re.I):
        return True
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return len(lines) >= 2


def parse_ima_series_reply(embed, series: str) -> SeriesLookupResult:
    """Parse $ima embed or plain-text body into series resolution or candidates."""
    series = (series or '').strip()
    if _is_ima_ambiguous_series_embed(embed):
        candidates = _parse_ima_series_candidates(embed)
        if candidates:
            return SeriesLookupResult(type='candidates', query=series, candidate_matches=candidates)
        raise MudaeError('Mudae returned multiple series matches but they could not be parsed')

    series_label = _ima_series_label_from_embed(embed, series)
    page_info = _footer_page_info(embed)
    first_page = _is_first_ima_page(page_info)
    names = parse_ima_names(
        embed,
        series_hint=series,
        series_label=series_label,
        first_page=first_page,
    )
    if names and _looks_like_ima_character_list(embed, names):
        return SeriesLookupResult(
            type='series',
            series_label=clean_series_label(series_label),
            query=series,
        )
    candidates = _parse_ima_series_candidates(embed)
    if candidates:
        return SeriesLookupResult(type='candidates', query=series, candidate_matches=candidates)
    if names:
        return SeriesLookupResult(
            type='series',
            series_label=clean_series_label(series_label),
            query=series,
        )
    raise MudaeError('Could not parse Mudae $ima reply')


def parse_ima_message(msg: discord.Message, series: str) -> SeriesLookupResult:
    embed = _ima_reply_embed(msg, series)
    return parse_ima_series_reply(embed, series)


def _is_blank_ima_line(raw: str) -> bool:
    if raw is None:
        return True
    if not raw.strip():
        return True
    return not _strip_md(raw)


def _is_first_ima_page(page_info: tuple[int, int] | None) -> bool:
    """Mudae uses 0- or 1-based page indexes depending on series."""
    if page_info is None:
        return True
    return page_info[0] <= 1


def _is_obvious_character_name(line: str) -> bool:
    if '(' in line and ')' in line:
        return True
    if re.search(r'-\d', line):
        return True
    s = line.strip()
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9]{1,7}', s):
        if re.fullmatch(r'[A-Z][a-z]+', s) and len(s) >= 5:
            return False
        return False
    if ' ' not in s and len(s) >= 5 and re.match(r'^[A-Za-z]', s):
        return True
    if ' ' in s:
        words = [w for w in s.split() if w]
        if words and any(len(w) > 5 for w in words):
            return True
    return False


def _line_is_short_multiword_alias(line: str) -> bool:
    """Multi-word series aliases like Ming Chao (not Character One)."""
    if '(' in line and ')' in line:
        return False
    if ' ' not in line:
        return False
    words = [w for w in line.split() if w]
    return bool(words) and all(len(w) <= 5 for w in words)


def _is_ima_noise_line(line: str, *, series_hint: str = '', series_label: str = '') -> bool:
    if not line:
        return True
    if _is_im_match_header(line):
        return True
    if re.search(r'\bpage\s*\d|\bcharacters?\b\s*:?\s*$', line, re.IGNORECASE) and len(line) < 50:
        return True
    if re.search(r'\b\d+\s*/\s*\d+\b', line):
        return True
    if '/' in line or '\\' in line:
        return True
    lc = line.casefold()
    for hint in (series_hint, series_label, clean_series_label(series_label)):
        h = (hint or '').strip().casefold()
        if not h:
            continue
        if lc == h:
            return True
        if lc.startswith(h) and re.search(r'\b\d+\s*/\s*\d+\b', line):
            return True
    return False


def _line_is_series_alias(line: str, *, series_hint: str = '', series_label: str = '') -> bool:
    """Alternate series title on $ima page 1 — not a character name."""
    line = line.strip()
    if not line:
        return False
    if '(' in line and ')' in line:
        return False
    lc = line.casefold()
    for hint in (series_hint, series_label, clean_series_label(series_label)):
        h = (hint or '').strip().casefold()
        if h and lc == h:
            return True
    # CJK-only titles (e.g. 鸣潮)
    if not re.search(r'[a-zA-Z]', line) and re.search(r'[\u4e00-\u9fff]', line):
        return True
    # Short latin acronym (e.g. WuWa) — not normal names like Aalto or Baizhi
    if re.fullmatch(r'[A-Za-z][A-Za-z0-9]{1,7}', line):
        if re.fullmatch(r'[A-Z][a-z]+', line) and len(line) >= 5:
            return False
        return True
    return False


def _drop_leading_series_aliases(
    lines: list[str],
    *,
    series_hint: str = '',
    series_label: str = '',
) -> list[str]:
    """First page without a blank gap: skip alias block before character names."""
    i = 0
    while i < len(lines):
        line = (lines[i] or '').strip()
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
    series_hint: str = '',
    series_label: str = '',
) -> list[str]:
    """Lines from $ima embed description that may contain character names."""
    raw_desc = desc or ''
    if not first_page:
        return [_strip_md(raw) for raw in raw_desc.splitlines()]

    # Paragraph break between aliases and characters
    if re.search(r'\n\s*\n', raw_desc):
        _prefix, suffix = re.split(r'\n\s*\n', raw_desc, maxsplit=1)
        return [_strip_md(raw) for raw in suffix.splitlines()]

    raw_lines = raw_desc.splitlines()
    gap_idx = next((i for i, raw in enumerate(raw_lines) if _is_blank_ima_line(raw)), None)
    if gap_idx is not None:
        return [_strip_md(raw) for raw in raw_lines[gap_idx + 1:]]

    stripped = [_strip_md(raw) for raw in raw_lines]
    return _drop_leading_series_aliases(
        stripped,
        series_hint=series_hint,
        series_label=series_label,
    )


def parse_ima_names(
    embed: discord.Embed,
    *,
    series_hint: str = '',
    series_label: str = '',
    first_page: bool = True,
) -> list[str]:
    desc = embed.description or ''
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
        if first_page and _line_is_series_alias(line, series_hint=series_hint, series_label=series_label):
            continue
        if first_page and _line_is_short_multiword_alias(line):
            continue
        line = re.sub(r'^\d+[\).\:\-]\s*', '', line)
        line = re.sub(r'^[-•*]\s*', '', line).strip()
        if ' - ' in line:
            left, right = line.split(' - ', 1)
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


def _ima_series_label_from_embed(embed: discord.Embed, fallback: str) -> str:
    return (
        _strip_md(embed.author.name if embed.author and embed.author.name else '')
        or _strip_md(embed.title or '')
        or fallback
    )


def _parse_ima_series_candidates(embed: discord.Embed) -> list[CandidateMatch]:
    """Parse ambiguous $ima series list (multiple series names, not characters)."""
    matches: list[CandidateMatch] = []
    seen: set[str] = set()
    for raw in _im_embed_text_lines(embed):
        line = _strip_md(raw)
        if not line or _is_im_match_header(line):
            continue
        if re.search(r'\bpage\b', line, re.I) and len(line) < 40:
            continue
        if re.search(r'\d+\s*/\s*\d+', line):
            continue
        line = re.sub(r'^\d+[\).\:\-]\s*', '', line)
        line = re.sub(r'^[-•*]\s*', '', line).strip()
        if len(line) < 2 or len(line) > 200:
            continue
        if line.lower() in ('n/a', 'none'):
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


def _looks_like_ima_character_list(embed: discord.Embed, names: list[str]) -> bool:
    if _is_ima_ambiguous_series_embed(embed):
        return False
    if _footer_page_info(embed) is not None:
        return True
    if _is_character_card(embed):
        return True
    return bool(names)


def _is_ima_ambiguous_series_embed(embed: discord.Embed) -> bool:
    if _footer_page_info(embed) is not None:
        return False
    if _is_character_card(embed):
        return False
    lines = [_strip_md(x) for x in _im_embed_text_lines(embed) if _strip_md(x)]
    if any(_is_im_match_header(l) for l in lines[:3]):
        return True
    series_option_lines = sum(
        1 for l in lines if _line_looks_like_ima_series_option(l)
    )
    if series_option_lines >= 2:
        return True
    return len(_parse_ima_series_candidates(embed)) >= 2


def _footer_page_info(embed: discord.Embed) -> tuple[int, int] | None:
    footer = embed.footer.text if embed.footer else ''
    m = re.search(r'(\d+)\s*/\s*(\d+)', footer)
    if m:
        return int(m.group(1)), int(m.group(2))
    for part in (
        embed.description or '',
        embed.title or '',
        _strip_md(embed.author.name if embed.author and embed.author.name else ''),
    ):
        m = re.search(r'(\d+)\s*/\s*(\d+)', part)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None


def clean_series_label(label: str) -> str:
    """Strip Mudae pagination suffixes like 'Silver Palace 0/8'."""
    s = (label or '').strip()
    cleaned = re.sub(r'\s+\d+\s*/\s*\d+\s*$', '', s).strip()
    return cleaned or s


class _MudaeSession:
    """On-demand discord.py-self connection: connect, query Mudae, disconnect."""

    def __init__(self) -> None:
        require_configured()
        self._client: Optional[discord.Client] = None
        self._channel: Optional[Union[discord.TextChannel, discord.Thread, discord.VoiceChannel]] = None
        self._mudae_id = _mudae_id()
        self._channel_id = _channel_id()
        self._ready = asyncio.Event()
        self._pending: Optional[asyncio.Future[discord.Message]] = None
        self._start_task: Optional[asyncio.Task] = None
        self._expect_message_id: Optional[int] = None
        self._watch_reactions_msg_id: Optional[int] = None
        self._reaction_notify: Optional[asyncio.Event] = None
        self._reply_not_before: Optional[float] = None

    def _message_in_target_channel(self, message: discord.Message) -> bool:
        ch = message.channel
        if ch.id == self._channel_id:
            return True
        parent_id = getattr(ch, 'parent_id', None)
        return parent_id == self._channel_id

    def _mudae_message_ready(self, message: discord.Message) -> bool:
        if message.embeds:
            return True
        content = (message.content or '').strip()
        if not content:
            return False
        if re.search(r'\d+\s+matches?\b', content, re.I):
            return True
        if ' - ' in content and len(content) > 10:
            return True
        return False

    async def _poll_recent_mudae_reply(self) -> Optional[discord.Message]:
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
                    print(f'[MUDAE] polled Mudae reply message {msg.id}', flush=True)
                    return msg
        except Exception as exc:
            print(f'[MUDAE] history poll failed: {type(exc).__name__}: {exc}', flush=True)
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

    async def _wait_for_nav_controls(
        self,
        msg: discord.Message,
        *,
        min_count: int = 2,
        timeout: float = IMA_REACTION_WAIT_S,
    ) -> discord.Message:
        """Wait until Mudae adds component buttons or custom-emoji reactions."""
        self._watch_reactions_msg_id = msg.id
        self._reaction_notify = asyncio.Event()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            _raise_if_series_cancelled()
            msg = await self._refresh_message(msg)
            if _mudae_nav_ready(msg, min_count):
                return msg
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(self._reaction_notify.wait(), timeout=min(0.4, remaining))
            except asyncio.TimeoutError:
                pass
            if self._reaction_notify:
                self._reaction_notify.clear()
        return msg

    async def _try_click_button(self, button: Button) -> bool:
        try:
            await button.click()
            label = button.label or button.emoji or button.custom_id
            print(f'[MUDAE] button.click() {label} on message {button.message.id}', flush=True)
            return True
        except Exception as exc:
            print(f'[MUDAE] button.click() failed: {type(exc).__name__}: {exc}', flush=True)
            return False

    async def _try_click_reaction(self, msg: discord.Message, reaction: discord.Reaction) -> bool:
        me = self._client.user if self._client else None
        try:
            if reaction.me and me is not None:
                await msg.remove_reaction(reaction.emoji, me)
                await _cancellable_sleep(0.15)
        except Exception as exc:
            print(f'[MUDAE] remove_reaction ({reaction.emoji}): {exc}', flush=True)
        try:
            await msg.add_reaction(reaction)
            print(f'[MUDAE] add_reaction {reaction.emoji} on message {msg.id}', flush=True)
            return True
        except Exception as exc:
            print(f'[MUDAE] add_reaction failed ({reaction.emoji}): {type(exc).__name__}: {exc}', flush=True)
            return False

    async def _click_mudae_page(self, msg: discord.Message, direction: str = 'next') -> bool:
        """Click Mudae nav control (component button preferred, else reaction)."""
        msg = await self._refresh_message(msg)
        buttons = _mudae_nav_buttons(msg)
        if len(buttons) >= 2:
            idx = 0 if direction == 'prev' else 1
            return await self._try_click_button(buttons[idx])
        reactions = _mudae_nav_reactions(msg)
        idx = 0 if direction == 'prev' else 1
        if len(reactions) <= idx:
            return False
        return await self._try_click_reaction(msg, reactions[idx])

    async def _wait_for_ima_embed_update(
        self,
        msg: discord.Message,
        prev_marker: str,
        prev_page_idx: int,
        timeout: float = REPLY_TIMEOUT_S,
    ) -> Optional[discord.Message]:
        """Wait for Mudae to edit the $ima embed after a nav click."""
        deadline = time.monotonic() + timeout
        loop = asyncio.get_running_loop()
        self._expect_message_id = msg.id
        self._pending = loop.create_future()

        async def _poll_for_edit() -> None:
            while not self._pending.done() and time.monotonic() < deadline:
                await asyncio.sleep(0.35)
                if self._pending.done():
                    return
                try:
                    fresh = await self._refresh_message(msg)
                    if _ima_embed_changed(fresh, prev_marker, prev_page_idx):
                        if not self._pending.done():
                            self._pending.set_result(fresh)
                        return
                except Exception:
                    pass

        poll_task = asyncio.create_task(_poll_for_edit())
        try:
            remaining = max(0.1, deadline - time.monotonic())
            return await asyncio.wait_for(self._pending, timeout=remaining)
        except asyncio.TimeoutError:
            return None
        finally:
            poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await poll_task
            self._expect_message_id = None
            self._pending = None

    async def _advance_ima_page(
        self,
        msg: discord.Message,
        embed: discord.Embed,
        page_info: tuple[int, int],
    ) -> tuple[discord.Message, discord.Embed] | None:
        """Click nav buttons/reactions until the $ima embed page changes."""
        prev_page_idx = page_info[0]
        prev_marker = _embed_marker(embed)

        msg = await self._wait_for_nav_controls(msg, min_count=2, timeout=IMA_REACTION_WAIT_S)
        buttons = _mudae_nav_buttons(msg)
        reactions = _mudae_nav_reactions(msg)
        use_buttons = len(buttons) >= 2

        if not use_buttons and len(reactions) < 2:
            print(
                f'[MUDAE] pagination: need 2 nav controls, have {len(buttons)} button(s) and '
                f'{len(reactions)} custom reaction(s) on message {msg.id}',
                flush=True,
            )
            return None

        controls: list = buttons if use_buttons else reactions
        mode = 'button' if use_buttons else 'reaction'
        try_indices = [1, 0] + [i for i in range(2, len(controls))]

        for idx in try_indices:
            if idx >= len(controls):
                continue
            _raise_if_series_cancelled()
            target = controls[idx]
            if mode == 'button':
                clicked = await self._try_click_button(target)
            else:
                clicked = await self._try_click_reaction(msg, target)
            if not clicked:
                continue

            await _cancellable_sleep(IMA_PAGE_DELAY_S - ACTION_DELAY_S)
            updated = await self._wait_for_ima_embed_update(msg, prev_marker, prev_page_idx)
            if updated is None or not updated.embeds:
                continue

            new_embed = updated.embeds[0]
            if _ima_embed_changed(updated, prev_marker, prev_page_idx):
                return updated, new_embed

        print(
            f'[MUDAE] pagination: no embed change after {mode} clicks on message {msg.id}',
            flush=True,
        )
        return None

    async def __aenter__(self) -> '_MudaeSession':
        # discord.py-self 2.1.0 has no Intents — user clients use plain Client().
        client = discord.Client()
        self._client = client

        @client.event
        async def on_ready():
            self._ready.set()

        @client.event
        async def on_message(message: discord.Message):
            await self._maybe_capture(message)

        @client.event
        async def on_message_edit(_before: discord.Message, after: discord.Message):
            await self._maybe_capture(after)

        @client.event
        async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
            if payload.message_id == self._watch_reactions_msg_id and self._reaction_notify:
                self._reaction_notify.set()

        self._start_task = asyncio.create_task(client.start(_token()))
        try:
            await asyncio.wait_for(self._ready.wait(), timeout=30.0)
        except asyncio.TimeoutError as e:
            await self._shutdown()
            raise MudaeError('Timed out connecting to Discord') from e
        except discord.LoginFailure as e:
            await self._shutdown()
            _log_mudae_error('Discord login failed', e)
            raise MudaeError(
                'Could not sign in to Discord. Check your setup in DEPLOY.md.'
            ) from e

        channel = client.get_channel(self._channel_id)
        if channel is None:
            try:
                channel = await client.fetch_channel(self._channel_id)
            except Exception as e:
                await self._shutdown()
                _log_mudae_error(f'could not open channel {self._channel_id}', e)
                raise MudaeError(
                    'Could not access the configured Discord channel. See DEPLOY.md.'
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
        print(f'[MUDAE] captured Mudae reply message {message.id} (embeds={len(message.embeds)})', flush=True)
        self._pending.set_result(message)

    async def _wait_for_pending_reply(self, timeout: float = REPLY_TIMEOUT_S) -> discord.Message:
        if self._pending is None:
            raise MudaeError('Internal error waiting for Mudae reply')
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
                    raise MudaeError('Timed out waiting for Mudae reply')
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
                    return await asyncio.wait_for(asyncio.shield(self._pending), timeout=min(0.25, remaining))
                except asyncio.TimeoutError:
                    if self._pending.done():
                        return self._pending.result()
                    continue
        except asyncio.CancelledError:
            raise MudaeCancelled('Series import cancelled by user') from None

    async def send_and_wait(
        self,
        content: str,
        timeout: float = REPLY_TIMEOUT_S,
        *,
        pause_before: bool = True,
    ) -> discord.Message:
        if self._channel is None:
            raise MudaeError('Discord channel not available')
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
                elif parse_ima_names(embed, series_hint='', series_label='', first_page=True):
                    return msg
            content = (msg.content or '').strip()
            if content and (self._mudae_message_ready(msg) or _ima_text_ready(content)):
                return msg
            await asyncio.sleep(0.35)
        return last

    async def lookup_im(self, name: str, *, pause_before: bool = True) -> LookupResult:
        name = (name or '').strip()
        if not name:
            raise MudaeError('Character name is required')
        _raise_if_series_cancelled()
        msg = await self.send_and_wait(f'$im {name}', pause_before=pause_before)
        msg = await self._ensure_embed_ready(msg)
        return parse_im_message(msg)

    async def resolve_character(self, name: str, *, fast: bool = False) -> CharacterInfo:
        """$im until a single character card; may follow first candidate."""
        pause = not fast
        result = await self.lookup_im(name, pause_before=pause)
        if result.type == 'character' and result.character:
            return result.character
        if result.candidates:
            if not fast:
                await self._action_pause()
            pick = im_lookup_name(result.candidates[0])
            result = await self.lookup_im(pick, pause_before=pause)
        if result.type == 'character' and result.character:
            return result.character
        raise MudaeError('Ambiguous or missing $im card')

    async def lookup_series(self, series: str) -> SeriesLookupResult:
        """$ima once — resolve an exact series or return ambiguous series options."""
        series = (series or '').strip()
        if not series:
            raise MudaeError('Series name is required')
        msg = await self.send_and_wait(f'$ima {series}')
        msg = await self._ensure_embed_ready(msg)
        return parse_ima_message(msg, series)

    async def list_series_characters(self, series: str) -> tuple[str, list[str]]:
        series = (series or '').strip()
        if not series:
            raise MudaeError('Series name is required')
        msg = await self.send_and_wait(f'$ima {series}')
        msg = await self._ensure_embed_ready(msg)
        has_component_embed = bool(msg.embeds)
        embed = _ima_reply_embed(msg, series)

        resolved = parse_ima_series_reply(embed, series)
        if resolved.type == 'candidates':
            raise MudaeAmbiguousSeries(series, resolved.candidate_matches)

        if has_component_embed:
            msg = await self._wait_for_nav_controls(msg)
            embed = msg.embeds[0]

        series_label = _ima_series_label_from_embed(embed, series)
        page_info = _footer_page_info(embed)
        first_page = _is_first_ima_page(page_info)
        names = parse_ima_names(
            embed,
            series_hint=series,
            series_label=series_label,
            first_page=first_page,
        )

        if not names and not _is_character_card(embed):
            raise MudaeError('Could not parse characters from $ima reply')

        all_names = list(names)
        pages_done = 1

        try:
            while page_info and page_info[0] < page_info[1] and pages_done < MAX_IMA_PAGES:
                _raise_if_series_cancelled()
                advanced = await self._advance_ima_page(msg, embed, page_info)
                if advanced is None:
                    break
                msg, embed = advanced
                more = parse_ima_names(
                    embed,
                    series_hint=series,
                    series_label=series_label,
                    first_page=False,
                )
                existing = {x.casefold() for x in all_names}
                for n in more:
                    if n.casefold() not in existing:
                        all_names.append(n)
                        existing.add(n.casefold())
                page_info = _footer_page_info(embed)
                if page_info is None:
                    break
                pages_done += 1
        except MudaeCancelled:
            if all_names:
                return clean_series_label(series_label), all_names
            raise

        if not all_names:
            raise MudaeError(f'No characters found for series "{series}"')
        return clean_series_label(series_label), all_names


def _run_async(coro):
    return asyncio.run(coro)


def with_discord_lock(fn: Callable[[], Any]) -> Any:
    require_configured()
    acquired = _lock.acquire(blocking=False)
    if not acquired:
        raise MudaeError('Another Mudae request is already in progress; try again shortly')
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


def lookup_series(series: str) -> SeriesLookupResult:
    def _do():
        async def _inner():
            async with _MudaeSession() as session:
                return await session.lookup_series(series)

        return _run_async(_inner())

    return with_discord_lock(_do)


def lookup_character_exact(name: str) -> CharacterInfo:
    result = lookup_character(name)
    if result.type == 'character' and result.character:
        return result.character
    cands = result.candidate_matches or [CandidateMatch(name=n) for n in (result.candidates or [])]
    labels = [c.label for c in cands[:20]]
    raise MudaeError(
        'Ambiguous character name; pick one: ' + ', '.join(labels)
        if labels
        else 'Character not found in Mudae'
    )


def list_series_and_lookup(
    series: str,
    *,
    on_character: Optional[Callable[[CharacterInfo], None]] = None,
    skip_names: Optional[set[str]] = None,
    max_retries: int = CHARACTER_LOOKUP_RETRIES,
    on_progress: Optional[Callable[[str, dict], None]] = None,
) -> dict[str, Any]:
    """
    $ima series then $im each character in one Discord session.
    on_character called for each successful character card (sync callback).
    on_progress(event, payload) for live UI updates (ima_complete, lookup_start, added, …).
    """
    skip = {n.casefold() for n in (skip_names or set())}

    def _emit(event: str, payload: dict) -> None:
        if on_progress:
            on_progress(event, payload)

    async def _add_one_with_retries(
        session: _MudaeSession,
        char_name: str,
        *,
        pacer: Optional[_ImPacer] = None,
    ) -> CharacterInfo:
        last_err = 'Unknown error'
        for attempt in range(max_retries + 1):
            _raise_if_series_cancelled()
            if attempt > 0:
                await _cancellable_sleep(IM_RETRY_DELAY_S)
                _emit('retry', {'name': char_name, 'attempt': attempt + 1})
            elif pacer is not None:
                await pacer.before_next()
            try:
                info = await session.resolve_character(
                    char_name,
                    fast=pacer is not None and attempt == 0,
                )
                if on_character:
                    on_character(info)
                if pacer is not None:
                    pacer.mark_done()
                return info
            except MudaeCancelled:
                raise
            except MudaeError as e:
                last_err = str(e)
            except Exception as e:
                _log_mudae_error(f'lookup failed for {char_name!r}', e)
                last_err = 'Could not look up character in Mudae'
        raise MudaeError(last_err)

    def _do():
        async def _inner():
            added: list[dict] = []
            skipped: list[str] = []
            failed: list[dict] = []
            cancelled = False
            series_label = series
            names: list[str] = []
            pacer = _ImPacer(IM_INTERVAL_S)
            async with _MudaeSession() as session:
                try:
                    series_label, names = await session.list_series_characters(series)
                except MudaeCancelled:
                    _emit('cancelled', {})
                    return {
                        'series': clean_series_label(series_label) if series_label else series,
                        'total_listed': 0,
                        'added': added,
                        'skipped': skipped,
                        'failed': failed,
                        'cancelled': True,
                    }
                _emit('ima_complete', {
                    'series': series_label,
                    'total_listed': len(names),
                })
                try:
                    await _cancellable_sleep(POST_IMA_TO_IM_DELAY_S)
                    _emit('ima_delay_done', {'seconds': POST_IMA_TO_IM_DELAY_S})

                    for char_name in names:
                        if is_series_cancelled():
                            cancelled = True
                            _emit('cancelled', {})
                            break
                        if char_name.casefold() in skip:
                            skipped.append(char_name)
                            _emit('skipped', {'name': char_name, 'reason': 'already in database'})
                            continue
                        _emit('lookup_start', {'name': char_name})
                        try:
                            info = await _add_one_with_retries(session, char_name, pacer=pacer)
                            added.append(info.to_dict())
                        except MudaeCancelled:
                            cancelled = True
                            _emit('cancelled', {})
                            break
                        except MudaeError as e:
                            err = {'name': char_name, 'error': str(e)}
                            failed.append(err)
                            _emit('failed', err)
                        except Exception as e:
                            err = {'name': char_name, 'error': str(e)}
                            failed.append(err)
                            _emit('failed', err)

                    if not cancelled and failed:
                        _emit('retry_pass_start', {'count': len(failed)})
                        retry_queue = list(failed)
                        failed = []
                        await _cancellable_sleep(IM_RETRY_DELAY_S)
                        for item in retry_queue:
                            if is_series_cancelled():
                                cancelled = True
                                _emit('cancelled', {})
                                break
                            char_name = item['name']
                            if char_name.casefold() in skip:
                                continue
                            _emit('lookup_start', {'name': char_name, 'retry': True})
                            try:
                                info = await _add_one_with_retries(session, char_name)
                                added.append(info.to_dict())
                            except MudaeCancelled:
                                cancelled = True
                                _emit('cancelled', {})
                                break
                            except MudaeError as e:
                                err = {'name': char_name, 'error': str(e)}
                                failed.append(err)
                                _emit('failed', err)
                            except Exception as e:
                                err = {'name': char_name, 'error': str(e)}
                                failed.append(err)
                                _emit('failed', err)
                except MudaeCancelled:
                    cancelled = True
                    _emit('cancelled', {})

            return {
                'series': series_label,
                'total_listed': len(names),
                'added': added,
                'skipped': skipped,
                'failed': failed,
                'cancelled': cancelled,
            }

        return _run_async(_inner())

    return with_discord_lock(_do)
