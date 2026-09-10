"""Structured logging.

The point of replacing ~100 `print()` calls was not tidiness: it was that a
mutation log with no actor is not an audit trail, and Phase 6 exists because
griefing has to be attributable. So the test that matters most here is that the
identity attaches by itself, without any call site having to remember.

The rest pin the logfmt encoding, because a value that silently breaks the
format is the kind of thing nobody notices until they need to grep for it.
"""

import logging

import pytest

import logs


@pytest.fixture
def captured():
    """Records formatted lines the way the real handler would emit them."""
    lines = []

    class _Capture(logging.Handler):
        def emit(self, record):
            lines.append(self.format(record))

    handler = _Capture()
    handler.setFormatter(logs.LogfmtFormatter())
    handler.addFilter(logs._RequestContextFilter())

    logger = logging.getLogger("test.logs")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    yield lines
    logger.handlers = []


@pytest.fixture
def log():
    return logs.get("test.logs")


class TestEncoding:
    def test_fields_become_key_value_pairs(self, log, captured):
        log.info("upload.accepted", character="Lucy", image_id=4213)
        assert "upload.accepted" in captured[0]
        assert "character=Lucy" in captured[0]
        assert "image_id=4213" in captured[0]

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("plain", "k=plain"),
            ("two words", 'k="two words"'),
            ('has "quotes"', r'k="has \"quotes\""'),
            ("a=b", 'k="a=b"'),
            ("line\nbreak", r'k="line\nbreak"'),
            ("", 'k=""'),
            (None, "k=-"),
            (True, "k=true"),
            (False, "k=false"),
            (0, "k=0"),
        ],
    )
    def test_values_that_would_break_the_format_are_quoted(self, log, captured, value, expected):
        log.info("event", k=value)
        assert expected in captured[0]

    def test_the_level_and_a_timestamp_are_always_present(self, log, captured):
        log.warning("something")
        assert "WARNING" in captured[0]
        assert captured[0].startswith("20")

    def test_an_exception_keeps_its_traceback(self, log, captured):
        try:
            raise ValueError("boom")
        except ValueError:
            log.exception("upload.failed", image_id=7)
        assert "image_id=7" in captured[0]
        assert "ValueError: boom" in captured[0]
        assert "Traceback" in captured[0]

    def test_logging_kwargs_are_not_swallowed_as_fields(self, log, captured):
        """exc_info belongs to logging, not to the event."""
        try:
            raise ValueError("boom")
        except ValueError:
            log.error("failed", exc_info=True)
        assert "exc_info" not in captured[0]
        assert "ValueError: boom" in captured[0]


class TestRequestContext:
    def test_the_actor_is_attached_without_the_call_site_asking(self, log, captured):
        """This is the audit trail. No route should have to remember to do it."""
        import identity
        import upload_imgchest

        with upload_imgchest.app.test_request_context("/api/hide-images"):
            identity.load_identity()
            log.info("moderation.hidden", image_id=42)

        assert "path=/api/hide-images" in captured[0]
        assert "actor=" in captured[0]
        assert "image_id=42" in captured[0]

    def test_outside_a_request_it_simply_says_less(self, log, captured):
        """Scripts and the self-bot log too, and must not blow up doing it."""
        log.info("startup")
        assert "actor=" not in captured[0]
        assert "path=" not in captured[0]

    def test_a_broken_context_never_breaks_the_log_call(self, log, captured, monkeypatch):
        """A logging call must never be what fails the request it describes."""
        import identity

        def exploding():
            raise RuntimeError("identity backend is down")

        monkeypatch.setattr(identity, "current_identity", exploding)
        import upload_imgchest

        with upload_imgchest.app.test_request_context("/api/customs"):
            log.info("customs.listed", count=3)

        assert "customs.listed" in captured[0]
        assert "count=3" in captured[0]


class TestSetup:
    def test_calling_it_twice_does_not_stack_handlers(self):
        logs._configured = False
        try:
            logs.setup()
            first = len(logging.getLogger().handlers)
            logs.setup()
            assert len(logging.getLogger().handlers) == first
        finally:
            logs._configured = True
