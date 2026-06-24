"""PAMPS strategy-search snapshot relay (Vercel serverless + KV).

The local strategy search POSTs its search.json here after each run (~every 2 min);
the deployed site GETs it for the "Strategy Search" panel.

  GET  /api/search                    -> latest search snapshot ({} if none)
  POST /api/search  (X-Push-Secret)   -> store snapshot
"""
from __future__ import annotations

import json
import os
import urllib.request
from http.server import BaseHTTPRequestHandler

KEY = "pamps:search"


def _kv_conn():
    url = (os.environ.get("KV_REST_API_URL")
           or os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip().rstrip("/")
    token = (os.environ.get("KV_REST_API_TOKEN")
             or os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if not url or not token:
        raise RuntimeError("KV not configured")
    return url, token


def kv(*args):
    url, token = _kv_conn()
    body = json.dumps([str(a) for a in args]).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError("KV error: " + str(data["error"]))
    return data.get("result") if isinstance(data, dict) else None


class handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        out = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        try:
            raw = kv("GET", KEY)
            self._json(200, json.loads(raw) if raw else {"empty": True})
        except RuntimeError:
            self._json(200, {"empty": True})
        except Exception:  # noqa: BLE001
            self._json(200, {"empty": True})

    def do_POST(self):
        secret = (os.environ.get("PAMPS_PUSH_SECRET") or "").strip()
        if not secret or self.headers.get("X-Push-Secret", "") != secret:
            self._json(403, {"error": "bad or missing X-Push-Secret"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            json.loads(body)
            kv("SET", KEY, body)
            self._json(200, {"ok": True})
        except RuntimeError:
            self._json(503, {"error": "KV not configured"})
        except Exception as exc:  # noqa: BLE001
            self._json(400, {"error": str(exc)})
