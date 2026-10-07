"""Vercel Python function: every /api/* route for FOMOCARD (see op/core.py)."""
import os
import sys
import traceback
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from op import core  # noqa: E402

MAX_BODY = 3_800_000


class handler(BaseHTTPRequestHandler):  # noqa: N801  (Vercel expects this name)
    def log_message(self, *a):  # quiet function logs
        return

    def _run(self, method):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path.rstrip("/") or "/"
        if path in ("/api/index", "/api") and q.get("route"):          # rewrite: /api/<route> -> /api/index?route=<route>
            path = "/api/" + q.pop("route")[0].strip("/")
        elif not path.startswith("/api/"):
            orig = self.headers.get("x-vercel-original-path") or self.headers.get("x-original-path") or ""
            if orig.startswith("/api/"):
                path = orig.split("?", 1)[0]
        body = None
        if method == "POST":
            n = int(self.headers.get("Content-Length", "0") or 0)
            if n > MAX_BODY:
                self.send_response(413)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = self.rfile.read(n) if n else b""
        try:
            code, ctype, payload, extra = core.dispatch(method, path, q, self.headers, body)
        except Exception:  # noqa: BLE001
            # never echo the exception: it can carry request headers, and so a key
            traceback.print_exc()
            code, ctype, payload, extra = 500, "application/json; charset=utf-8", b'{"ok": false, "error": "server error"}', {}
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def do_GET(self):  # noqa: N802
        self._run("GET")

    def do_POST(self):  # noqa: N802
        self._run("POST")

    def do_OPTIONS(self):  # noqa: N802
        self._run("OPTIONS")

    def do_HEAD(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", "0")
        self.end_headers()
