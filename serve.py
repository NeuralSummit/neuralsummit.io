#!/usr/bin/env python3
"""Serve the built site (public/) locally the way GitHub Pages will: over http, so moving between pages swaps them
in place (site.js can't fetch from file://), and with byte ranges, so the listening player can scrub through a card's
audio (Python's own http.server sends whole files only, and browsers then can't seek).

    python3 serve.py [port]      # default 8000, on this machine only: http://localhost:8000
"""
import http.server
import io
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "public"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(ROOT), **k)

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        path = self.translate_path(self.path)
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", (self.headers.get("Range") or "").strip())
        if not m or not os.path.isfile(path) or not (m[1] or m[2]):
            return super().send_head()
        size = os.path.getsize(path)
        start, end = (int(m[1]), int(m[2]) if m[2] else size - 1) if m[1] else (max(0, size - int(m[2])), size - 1)
        end = min(end, size - 1)
        if start > end:
            self.send_error(416)
            return None
        with open(path, "rb") as f:
            f.seek(start)
            part = f.read(end - start + 1)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(len(part)))
        self.end_headers()
        return io.BytesIO(part)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    print(f"Serving {ROOT} at http://localhost:{port}")
    http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
