"""WSGI entry point.

Gunicorn is invoked as `gunicorn app:app` — this module, then the `app`
attribute. The import below therefore looks unused to a linter but is the
entire purpose of the file; removing it breaks every deployment.
"""

from upload_imgchest import app

__all__ = ["app"]
