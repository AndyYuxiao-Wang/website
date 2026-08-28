"""
Local static server for the whole personal site (home, blog, and the
election map app under app/).

Fetches (map SVGs, election JSON, etc.) won't work from a file:// page, so
run this instead of double-clicking index.html.

    py serve.py
"""
import http.server
import socketserver
import webbrowser
from pathlib import Path

PORT = 8001
DIRECTORY = Path(__file__).resolve().parent


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DIRECTORY), **kwargs)


if __name__ == "__main__":
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        url = f"http://localhost:{PORT}/index.html"
        print(f"Serving {DIRECTORY} at {url}")
        webbrowser.open(url)
        httpd.serve_forever()
