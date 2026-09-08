"""Web server entry point for DigitalOcean App Platform and local use."""
from upload_imgchest import app

# Gunicorn uses: gunicorn app:app (this module, app object)
