"""Route blueprints.

Every route used to be declared with `@app.route`, which needs the app object to
already exist — so all 46 of them had to live below `app = Flask(__name__)` in
one 1,700-line module. A Blueprint records the same declarations without an app,
and `upload_imgchest` attaches them once at startup, so the import only ever
goes one way: a blueprint knows nothing about the app that will register it.

Paths are unchanged. What each blueprint owns is a subject, not a URL prefix.
"""
