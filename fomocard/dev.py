"""Local preview of the FOMOCARD site, with the same routing as Vercel.

Serves fomocard/web and answers /api/* with the site's own backend (web/op),
which is what web/api/index.py does in production.

  py fomocard/dev.py                      # http://localhost:4181
  set FOMOCARD_DRY=1 & py fomocard/dev.py # test mode, nothing is broadcast
"""
import http.server
import json
import os
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

WEB = Path(__file__).resolve().parent / "web"
sys.path.insert(0, str(WEB))
# local test data lives next to this script, never inside web/ (which is deployed)
os.environ.setdefault("OP_STATE_FILE", str(Path(__file__).resolve().parent / "dev_state.json"))
from op import core  # noqa: E402

PORT = int(os.environ.get("PORT", "4181"))
PAGES = {"/access": "/access.html", "/docs": "/docs.html"}


class H(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(WEB), **k)

    def _api(self, method):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(n) if n else None
        try:
            code, ctype, payload, extra = core.dispatch(method, u.path.rstrip("/"), parse_qs(u.query), self.headers, body)
        except Exception as exc:  # noqa: BLE001
            code, ctype, payload, extra = 500, "application/json", json.dumps({"ok": False, "error": str(exc)[:200]}).encode(), {}
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        for k, v in extra.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(payload)

    def _route(self):
        p = self.path.split("?", 1)[0].rstrip("/") or "/"
        if p in PAGES:
            self.path = PAGES[p] + self.path[len(p):]
        return self.path.startswith("/api/")

    def do_GET(self):  # noqa: N802
        if self._route():
            return self._api("GET")
        super().do_GET()

    def do_POST(self):  # noqa: N802
        if self._route():
            return self._api("POST")
        self.send_error(405)


if __name__ == "__main__":
    print(f"FOMOCARD on http://localhost:{PORT}  ({'test mode' if core.DRY else 'LIVE payments'})")
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
