"""Application logging.

Replaces ~100 `print(..., flush=True)` calls. Three things were wrong with
those, in increasing order of importance:

- **No levels.** A rejected upload and a routine "temp file written" were the
  same kind of line, so there was no way to ask for only the interesting ones.
- **No structure.** Everything was prose, so answering "what happened to image
  4213" meant grepping for a substring and hoping the message had not been
  reworded since.
- **No identity.** Nothing recorded *who* removed an image. Since the whole
  point of Phase 6 was that griefing has to be attributable, mutation logs
  without an actor are not an audit trail at all.

Output is logfmt — `event key=value key=value` — rather than JSON, because
these go to journald and are read with `journalctl -u imgmanager`. Logfmt stays
readable by eye there and greps cleanly; JSON would be noise in a terminal and
buys nothing until there is a log service to ship to.

Usage:

    log = logs.get(__name__)
    log.info("upload.accepted", character="Lucy", image_id=4213)

Identity and request path are attached automatically inside a request, so no
call site has to remember to include them.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime

# kwargs that belong to logging itself and must not be swallowed as fields.
_RESERVED = ("exc_info", "stack_info", "stacklevel", "extra")

_configured = False


def _quote(value: object) -> str:
    """logfmt values: bare when simple, quoted when they would break parsing."""
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    if text == "":
        return '""'
    if any(c in text for c in ' =")') or "\n" in text:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        return f'"{escaped}"'
    return text


class _RequestContextFilter(logging.Filter):
    """Attach who and what, when there is a request to ask.

    Imported lazily and guarded: this module is used by scripts and by tests
    that never build an app, and logging must never be the thing that raises.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.context = {}
        try:
            from flask import has_request_context, request

            if not has_request_context():
                return True
            record.context["path"] = request.path

            import identity

            me = identity.current_identity()
            if me is not None:
                record.context["actor"] = me.handle
        except Exception:
            # A logging call must never fail the request it is describing.
            pass
        return True


class LogfmtFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        stamp = datetime.fromtimestamp(record.created, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts = [stamp, record.levelname, record.getMessage()]

        for key, value in {**getattr(record, "context", {}), **getattr(record, "fields", {})}.items():
            parts.append(f"{key}={_quote(value)}")

        line = " ".join(parts)
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class _FieldAdapter(logging.LoggerAdapter):
    """Lets call sites write `log.info("event", key=value)`.

    stdlib logging takes structure only through `extra=`, which is verbose
    enough at the call site that people stop bothering — which is how the prose
    messages happened in the first place.
    """

    def process(self, msg, kwargs):
        fields = {k: kwargs.pop(k) for k in list(kwargs) if k not in _RESERVED}
        extra = kwargs.setdefault("extra", {})
        extra["fields"] = fields
        return msg, kwargs


def setup(level: str | None = None) -> None:
    """Configure the root logger. Safe to call more than once."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(LogfmtFormatter())
    handler.addFilter(_RequestContextFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel((level or os.environ.get("LOG_LEVEL") or "INFO").upper())

    # Werkzeug logs one line per request in dev; gunicorn's access log covers
    # production and is configured separately in gunicorn.conf.py.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    _configured = True


def get(name: str) -> _FieldAdapter:
    return _FieldAdapter(logging.getLogger(name), {})
