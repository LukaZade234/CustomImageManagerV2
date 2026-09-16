"""The dedicated Mudae service: protocol, queue, idle disconnect, and the client.

The point of the service is that it is the *only* thing that talks to Discord, so
these tests cover the two things that could quietly break that promise: whether a
job is answered at all, and whether the account is left connected longer than it
should be. The web side is tested through the real socket where it matters, so a
change to the wire format cannot pass unnoticed.
"""

import asyncio
import json
import threading

import pytest

import mudae_discord
import mudae_service


class _FakeSession:
    def __init__(self, *, on_lookup=None):
        self.connected = False
        self.closed = False
        self.lookups = []
        self.series = []
        self._on_lookup = on_lookup

    async def connect(self):
        self.connected = True
        return self

    async def close(self):
        self.closed = True

    async def lookup_im(self, name):
        self.lookups.append(name)
        if self._on_lookup is not None:
            await self._on_lookup(name)
        return mudae_discord.LookupResult(
            type="character", character=mudae_discord.CharacterInfo(name=name)
        )

    async def fetch_series_extract_dm(self, series):
        self.series.append(series)
        return f"EXTRACT:{series}"


async def _call(path, op, **args):
    reader, writer = await asyncio.open_unix_connection(path)
    writer.write((json.dumps({"op": op, "args": args}) + "\n").encode())
    await writer.drain()
    line = await reader.readline()
    writer.close()
    await writer.wait_closed()
    return json.loads(line)


def _started(tmp_path, **kwargs):
    """A service on a temp socket, cleaned up by the caller's `finally`."""

    async def _scenario(body):
        service = mudae_service.MudaeService(**kwargs)
        path = str(tmp_path / "mudae.sock")
        await service.start(path)
        try:
            return await body(service, path)
        finally:
            await service.stop()

    return _scenario


class TestJobRoundTrip:
    def test_a_lookup_connects_runs_and_answers(self, tmp_path):
        fake = _FakeSession()

        async def body(service, path):
            return await _call(path, "lookup", name="Rem")

        reply = asyncio.run(_started(tmp_path, session_factory=lambda: fake, idle_seconds=60)(body))

        assert reply == {
            "ok": True,
            "data": {
                "type": "character",
                "character": {
                    "name": "Rem",
                    "series": "",
                    "rank": "",
                    "image_url": "",
                    "is_female": False,
                    "is_male": False,
                    "pools": "",
                },
            },
        }
        assert fake.connected is True
        assert fake.lookups == ["Rem"]
        # stop() is the shutdown path; the account must not be left signed in.
        assert fake.closed is True

    def test_a_series_fetch_returns_the_raw_dm(self, tmp_path):
        fake = _FakeSession()

        async def body(service, path):
            return await _call(path, "series_extract", series="Lord of the Mysteries")

        reply = asyncio.run(_started(tmp_path, session_factory=lambda: fake, idle_seconds=60)(body))

        assert reply == {"ok": True, "data": "EXTRACT:Lord of the Mysteries"}
        assert fake.series == ["Lord of the Mysteries"]

    def test_an_unknown_operation_is_refused(self, tmp_path):
        async def body(service, path):
            return await _call(path, "delete-everything")

        reply = asyncio.run(_started(tmp_path, session_factory=_FakeSession, idle_seconds=60)(body))

        assert reply["ok"] is False
        assert reply["kind"] == "bad_request"

    def test_a_failing_session_becomes_an_error_reply_not_a_crash(self, tmp_path):
        class _Broken(_FakeSession):
            async def lookup_im(self, name):
                raise mudae_discord.MudaeError("Character not found in Mudae")

        async def body(service, path):
            return await _call(path, "lookup", name="Nobody")

        reply = asyncio.run(_started(tmp_path, session_factory=_Broken, idle_seconds=60)(body))

        assert reply == {"ok": False, "kind": "mudae", "error": "Character not found in Mudae"}


class TestLazyConnectAndIdle:
    def test_the_client_is_not_signed_in_before_the_first_job(self, tmp_path):
        fake = _FakeSession()

        async def body(service, path):
            return await _call(path, "status")

        reply = asyncio.run(_started(tmp_path, session_factory=lambda: fake, idle_seconds=60)(body))

        assert reply["data"]["connected"] is False
        assert fake.connected is False

    def test_it_disconnects_after_the_idle_window(self, tmp_path):
        fake = _FakeSession()

        async def body(service, path):
            await _call(path, "lookup", name="Rem")
            await asyncio.sleep(0.5)
            return await _call(path, "status")

        reply = asyncio.run(
            _started(tmp_path, session_factory=lambda: fake, idle_seconds=0.15)(body)
        )

        assert fake.closed is True
        assert reply["data"]["connected"] is False

    def test_a_second_job_reuses_the_connection(self, tmp_path):
        fake = _FakeSession()

        async def body(service, path):
            await _call(path, "lookup", name="Rem")
            await _call(path, "lookup", name="Ram")
            return await _call(path, "status")

        reply = asyncio.run(_started(tmp_path, session_factory=lambda: fake, idle_seconds=60)(body))

        assert fake.lookups == ["Rem", "Ram"]
        assert reply["data"]["connected"] is True


class TestQueue:
    def test_a_full_queue_is_refused_rather_than_piled_up(self, tmp_path):
        gate = asyncio.Event()

        async def slow_lookup(_name):
            await gate.wait()

        async def body(service, path):
            first = asyncio.create_task(_call(path, "lookup", name="A"))
            await asyncio.sleep(0.05)  # A is now running
            second = asyncio.create_task(_call(path, "lookup", name="B"))
            await asyncio.sleep(0.05)  # B is now waiting
            third = await _call(path, "lookup", name="C")  # one over the cap
            gate.set()
            return third, await asyncio.gather(first, second)

        third, ran = asyncio.run(
            _started(
                tmp_path,
                session_factory=lambda: _FakeSession(on_lookup=slow_lookup),
                idle_seconds=60,
                queue_max=1,
                job_timeout=5,
            )(body)
        )

        assert third["ok"] is False
        assert third["kind"] == "busy"
        assert all(reply["ok"] for reply in ran)


class _ServiceThread:
    """Runs the real service in a thread so the blocking web client can use it."""

    def __init__(self, path, **kwargs):
        self.path = path
        self.service = mudae_service.MudaeService(**kwargs)
        self._ready = threading.Event()
        self._loop = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        loop.run_until_complete(self.service.start(self.path))
        self._ready.set()
        loop.run_forever()
        loop.run_until_complete(self.service.stop())
        loop.close()

    def __enter__(self):
        self._thread.start()
        assert self._ready.wait(5), "service did not start"
        return self

    def __exit__(self, *exc):
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)


class TestWebClient:
    def test_a_lookup_is_rehydrated_from_the_socket(self, tmp_path, monkeypatch):
        fake = _FakeSession()
        path = str(tmp_path / "mudae.sock")

        with _ServiceThread(path, session_factory=lambda: fake, idle_seconds=60):
            monkeypatch.setenv("MUDAE_SOCKET", path)
            result = mudae_discord.lookup_character("Rem")
            status = mudae_discord.status()

        assert isinstance(result, mudae_discord.LookupResult)
        assert isinstance(result.character, mudae_discord.CharacterInfo)
        assert result.character.name == "Rem"
        assert status["configured"] is True
        assert status["mode"] == "service"
        assert status["connected"] is True

    def test_a_series_fetch_returns_the_text(self, tmp_path, monkeypatch):
        path = str(tmp_path / "mudae.sock")

        with _ServiceThread(path, session_factory=_FakeSession, idle_seconds=60):
            monkeypatch.setenv("MUDAE_SOCKET", path)
            text = mudae_discord.fetch_series_extract("Bleach")

        assert text == "EXTRACT:Bleach"

    def test_a_missing_service_is_a_clear_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUDAE_SOCKET", str(tmp_path / "absent.sock"))

        with pytest.raises(mudae_discord.MudaeError) as caught:
            mudae_discord.lookup_character("Rem")

        assert "not running" in str(caught.value)

    def test_status_reports_a_dead_service_as_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MUDAE_SOCKET", str(tmp_path / "absent.sock"))

        status = mudae_discord.status()

        assert status["configured"] is False
        assert status["mode"] == "service"

    def test_without_a_socket_mudae_is_unavailable(self, monkeypatch):
        monkeypatch.delenv("MUDAE_SOCKET", raising=False)

        assert mudae_discord.configured() is False
        assert mudae_discord.status() == {
            "configured": False,
            "mode": "service",
            "error": "MUDAE_SOCKET is not set",
        }
        with pytest.raises(mudae_discord.MudaeError):
            mudae_discord.lookup_character("Rem")
        with pytest.raises(mudae_discord.MudaeError):
            mudae_discord.fetch_series_extract("Bleach")
