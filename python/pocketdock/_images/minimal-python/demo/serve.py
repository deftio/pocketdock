"""Minimal web server for the pocketdock demo."""

import http.server
import os

PORT = 8000
DIRECTORY = os.path.dirname(os.path.abspath(__file__)) or "."


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, directory=DIRECTORY, **kwargs)


if __name__ == "__main__":
    print(f"Serving demo on http://0.0.0.0:{PORT} ...")
    print("Open http://localhost:8080 on your host (if you mapped -p 8080:8000)")
    http.server.HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()  # nosec B104
