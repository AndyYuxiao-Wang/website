"""
Local static server for the election map.

The page fetches its maps and datasets as separate files, so opening
index.html directly (file://) won't work in most browsers. Run this
instead, then open the printed URL.

    py serve.py
"""
import http.server
import socketserver
import webbrowser
from pathlib import Path

PORT = 8000
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
