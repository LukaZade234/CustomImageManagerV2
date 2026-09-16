"""Dedicated Mudae worker.

The Discord self-bot cannot be run straight from the web app. gunicorn runs two
workers, so the process-global lock in `mudae_discord` only serializes within
one of them, and every lookup pays a fresh Discord *identify* against a
~1000/day budget. This process is the single owner of the connection: web
workers forward jobs over a Unix socket and it runs them one at a time.

The account is deliberately **not** online around the clock. The client connects
when the first job arrives and disconnects once the queue has been empty for
`MUDAE_IDLE_SECONDS` (default 600), so an idle site is not a constant self-bot
presence. See `docs/DECISIONS.md`, "The self-bot is a liability".

Run it with `python mudae_service.py --socket /var/lib/imgmanager/mudae.sock`
(the socket path also comes from `MUDAE_SOCKET`). It needs the same
`DISCORD_USER_TOKEN` / `DISCORD_CHANNEL_ID` the web app used to need.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import logs
import mudae_discord
from mudae_discord import MudaeError

log = logs.get(__name__)

_OPS = ("lookup", "series_extract")
_MAX_REQUEST_BYTES = 64 * 1024
_READ_TIMEOUT_S = 15.0
_WATCHDOG_TICK_S = 5.0


@dataclass
class _Job:
    op: str
    args: dict[str, Any]
    future: asyncio.Future


def _error_reply(exc: Exception) -> dict:
    if isinstance(exc, MudaeError):
        return {"ok": False, "kind": "mudae", "error": str(exc)}
    log.warning("mudae.service_job_failed", error=f"{type(exc).__name__}: {exc}")
    return {"ok": False, "kind": "error", "error": "Mudae failed unexpectedly. Try again."}


class MudaeService:
    """Owns one Discord connection and runs queued jobs against it."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] | None = None,
        idle_seconds: float | None = None,
        queue_max: int | None = None,
        job_timeout: float | None = None,
    ) -> None:
        self._session_factory = session_factory or mudae_discord._MudaeSession
        self._idle = float(mudae_discord.idle_seconds() if idle_seconds is None else idle_seconds)
        self._queue_max = int(mudae_discord.queue_max() if queue_max is None else queue_max)
        self._job_timeout = float(
            mudae_discord.job_timeout() if job_timeout is None else job_timeout
        )
        self._queue: asyncio.Queue[_Job] = asyncio.Queue()
        self._session: Any = None
        self._connected = False
        self._busy = False
        self._last_activity = time.monotonic()
        self._server: asyncio.AbstractServer | None = None
        self._tasks: list[asyncio.Task] = []

    # --- Lifecycle ------------------------------------------------------

    async def start(self, path: str) -> None:
        if os.path.exists(path):
            os.unlink(path)
        self._last_activity = time.monotonic()
        self._server = await asyncio.start_unix_server(self._on_client, path=path)
        os.chmod(path, 0o600)
        self._tasks = [
            asyncio.create_task(self._worker(), name="mudae-worker"),
            asyncio.create_task(self._idle_watchdog(), name="mudae-idle"),
        ]
        log.info("mudae.service_started", socket=path, idle_seconds=self._idle)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        await self._disconnect("shutdown")
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    def status(self) -> dict[str, Any]:
        now = time.monotonic()
        idle_for = now - self._last_activity
        return {
            "connected": self._connected,
            "busy": self._busy,
            "queue": self._queue.qsize(),
            "queue_max": self._queue_max,
            "idle_seconds": round(self._idle, 1),
            "idle_remaining": round(max(0.0, self._idle - idle_for), 1) if self._connected else 0.0,
        }

    # --- Queue ----------------------------------------------------------

    async def _worker(self) -> None:
        while True:
            job = await self._queue.get()
            self._busy = True
            try:
                await self._ensure_connected()
                reply = await self._run_job(job)
            except Exception as exc:  # a bad job must not kill the worker
                reply = _error_reply(exc)
            finally:
                self._busy = False
                self._last_activity = time.monotonic()
                self._queue.task_done()
            if not job.future.done():
                job.future.set_result(reply)

    async def _run_job(self, job: _Job) -> dict:
        if job.op == "lookup":
            result = await self._session.lookup_im(str(job.args.get("name") or ""))
            return {"ok": True, "data": result.to_dict()}
        if job.op == "series_extract":
            text = await self._session.fetch_series_extract_dm(str(job.args.get("series") or ""))
            return {"ok": True, "data": text}
        return {"ok": False, "kind": "bad_request", "error": f"Unknown operation {job.op!r}"}

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        session = self._session_factory()
        await session.connect()
        self._session = session
        self._connected = True
        log.info("mudae.connected")

    async def _disconnect(self, reason: str) -> None:
        session, self._session = self._session, None
        self._connected = False
        if session is None:
            return
        try:
            await session.close()
        except Exception as exc:
            log.warning("mudae.disconnect_failed", error=f"{type(exc).__name__}: {exc}")
        log.info("mudae.disconnected", reason=reason)

    async def _idle_watchdog(self) -> None:
        tick = max(0.05, min(_WATCHDOG_TICK_S, self._idle or _WATCHDOG_TICK_S))
        while True:
            await asyncio.sleep(tick)
            if not self._connected or self._busy or not self._queue.empty():
                continue
            if time.monotonic() - self._last_activity >= self._idle:
                await self._disconnect("idle")

    # --- Socket protocol ------------------------------------------------

    async def _on_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await asyncio.wait_for(reader.readline(), timeout=_READ_TIMEOUT_S)
            if not raw or len(raw) > _MAX_REQUEST_BYTES:
                return
            reply = await self._dispatch(json.loads(raw.decode()))
        except Exception as exc:  # one bad request must not take the server down
            reply = _error_reply(exc)
        try:
            writer.write((json.dumps(reply) + "\n").encode())
            await writer.drain()
        except (ConnectionError, OSError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError):
                pass

    async def _dispatch(self, request: Any) -> dict:
        if not isinstance(request, dict):
            return {"ok": False, "kind": "bad_request", "error": "Malformed request"}
        op = request.get("op")
        args = request.get("args") or {}
        if op == "status":
            return {"ok": True, "data": self.status()}
        if op not in _OPS:
            return {"ok": False, "kind": "bad_request", "error": f"Unknown operation {op!r}"}
        if self._queue.qsize() >= self._queue_max:
            return {
                "ok": False,
                "kind": "busy",
                "error": "Mudae is handling other requests; try again shortly.",
            }
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        await self._queue.put(_Job(op=op, args=args, future=future))
        try:
            return await asyncio.wait_for(future, timeout=self._job_timeout)
        except TimeoutError:
            future.cancel()
            return {
                "ok": False,
                "kind": "timeout",
                "error": "Mudae did not answer in time. Try again.",
            }


async def _serve(path: str) -> None:
    service = MudaeService()
    await service.start(path)
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:  # not the main thread on some platforms
            pass
    try:
        await stop_event.wait()
    finally:
        await service.stop()
        log.info("mudae.service_stopped")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dedicated Mudae / Discord worker.")
    parser.add_argument(
        "--socket",
        default=mudae_discord.socket_path() or "/var/lib/imgmanager/mudae.sock",
        help="Unix socket to listen on (default: $MUDAE_SOCKET)",
    )
    args = parser.parse_args(argv)
    logs.setup()
    if not mudae_discord._token() or not mudae_discord._channel_id():
        log.warning(
            "mudae.service_unconfigured", hint="set DISCORD_USER_TOKEN / DISCORD_CHANNEL_ID"
        )
    asyncio.run(_serve(args.socket))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
