"""Gunicorn configuration.

Why threads rather than sync workers
------------------------------------
A sync worker handles one request from first byte to last and is blocked for the
whole of it, including time spent purely *waiting* on the network. Nearly
everything slow here is waiting -- ImgChest uploads, Discord replies -- so
`--workers 2` meant **two concurrent requests site-wide**, and one series import
plus one upload made the site unresponsive for everyone else.

Threads fix that cheaply: Python releases the GIL while waiting on I/O, and
Pillow releases it while encoding, so both the waiting and the image work
overlap. `workers x threads` requests can now be in flight at once.

Why not gevent
--------------
gevent monkey-patches sockets, which conflicts with the `asyncio.run()` Discord
client in mudae_discord.py. gthread patches nothing.

Why the timeout stopped killing long imports
--------------------------------------------
Gunicorn kills a worker that goes silent for `timeout` seconds. A *sync* worker
only reports in between requests, so any request over the limit was killed
mid-flight -- which is why series imports longer than two minutes died with no
error. A *gthread* worker reports from its accept loop, independently of the
requests its threads are serving, so long responses no longer trip it. Verified:
under sync a 12s response was cut off at 5s with WORKER TIMEOUT; under gthread it
completed.

The timeout still does its real job: catching a genuinely wedged process.

This is a mitigation, not the cure. The cure is not doing minutes of work inside
a web request at all -- see Phase 8 in docs/ROADMAP.md.
"""

import multiprocessing
import os


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


# Localhost only. Nothing should reach the app except cloudflared, which
# connects from this machine -- the tunnel dials out to Cloudflare rather than
# accepting connections. Binding 0.0.0.0 would leave the origin exposed the
# moment the cloud firewall was misconfigured, and traffic arriving that way
# would bypass Cloudflare entirely: no edge caching, no DDoS protection, and
# the real origin address discoverable by a port scan.
#
# Override only if something genuinely off-box must reach it directly.
bind = f"{os.environ.get('WEB_BIND_HOST', '127.0.0.1')}:{os.environ.get('PORT', '8080')}"

# Two processes give crash resilience: if one dies the other keeps serving while
# gunicorn restarts it. More than that buys little, because the threads below
# already provide the concurrency and the box is small.
workers = _int_env("WEB_WORKERS", min(2, multiprocessing.cpu_count()))

worker_class = "gthread"
threads = _int_env("WEB_THREADS", 8)

# Long enough for a slow ImgChest upload to finish; only trips on a wedged
# process now that long responses no longer starve the heartbeat.
timeout = _int_env("WEB_TIMEOUT", 120)
graceful_timeout = 30

# Heartbeat file in shared memory rather than on disk.
worker_tmp_dir = "/dev/shm" if os.path.isdir("/dev/shm") else None

# Recycle workers occasionally so a slow leak in the image pipeline cannot grow
# without bound. The jitter stops every worker restarting at the same moment.
max_requests = _int_env("WEB_MAX_REQUESTS", 1000)
max_requests_jitter = 100

# Each thread opens its own SQLite connection lazily, so nothing is inherited
# across the fork. Left off anyway to avoid fork-safety surprises with the
# Discord client's event loop.
preload_app = False

accesslog = os.environ.get("WEB_ACCESS_LOG") or None
errorlog = "-"
loglevel = os.environ.get("WEB_LOG_LEVEL", "info")
