"""Background worker for the V43 accent (see accent_v43.py, docs/ACCENT.md section 29).

The V43 accent needs two models -- a cut-out and a face parser -- that take about
1.9 GB of memory and a second or more per image, so it can never run inside a web
request. With ACCENT_ENGINE=v43 the gallery endpoint queues a character whose seed
is stale (new images, a new main image, or a seed from the original extractor) and
serves the stored seed; this process works through that queue:

- runs the models on each image that has no stored data yet, once, and keeps what
  they found (accent_image_data / accent_main_data);
- recomputes the character from the stored data and writes the seed;
- retries a failure later, with backoff, and never overwrites a hand-picked colour.

It runs as its own service (deploy/imgmanager-accent.service) so the web workers
never load the models, and gives their memory back after a quiet spell.

    python accent_worker.py            # run until stopped
    python accent_worker.py --once     # drain the queue, then exit
"""

from __future__ import annotations

import argparse
import gc
import signal
import sys
import time
from datetime import UTC, datetime, timedelta

import logs

log = logs.get(__name__)

POLL_SECONDS = 15
IDLE_UNLOAD_SECONDS = 600  # models are released after this long with nothing to do
RETRY_BASE = timedelta(minutes=5)
RETRY_MAX = timedelta(hours=24)


def _retry_at(attempts: int) -> str:
    delay = min(RETRY_MAX, RETRY_BASE * (2**attempts))
    return (datetime.now(UTC) + delay).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def run_once(models) -> bool:
    """Process the most due job. False when there was nothing to do."""
    import accent_extract
    import db

    job = db.next_accent_job()
    if job is None:
        return False
    character_id, name, attempts = job
    started = time.monotonic()
    try:
        accent_extract.recompute_accent_v43(name, models)
    except Exception as e:
        log.exception("accent.worker_failed", character=name, attempts=attempts + 1)
        db.fail_accent_job(character_id, f"{type(e).__name__}: {e}", _retry_at(attempts))
        return True
    db.finish_accent_job(character_id)
    log.info(
        "accent.worker_done",
        character=name,
        seconds=round(time.monotonic() - started, 1),
        queued=db.accent_queue_size(),
    )
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Accent worker (V43).")
    parser.add_argument("--once", action="store_true", help="drain the queue, then exit")
    args = parser.parse_args(argv)
    logs.setup()

    import accent_models

    stop = False

    def _stop(*_):
        nonlocal stop
        stop = True

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, _stop)

    while not stop:
        try:
            accent_models.ensure_models()
            break
        except Exception:
            if args.once:
                raise
            log.exception("accent.models_unavailable")
            time.sleep(300)

    models = accent_models.Models()
    idle_since = time.monotonic()
    while not stop:
        if run_once(models):
            idle_since = time.monotonic()
            continue
        if args.once:
            break
        if models.loaded and time.monotonic() - idle_since > IDLE_UNLOAD_SECONDS:
            models.unload()
            gc.collect()
            log.info("accent.models_released")
        time.sleep(POLL_SECONDS)
    return 0


if __name__ == "__main__":
    sys.exit(main())
