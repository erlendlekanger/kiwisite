"""Vercel serverless function: GET /api/config — token + threshold info."""
from http.server import BaseHTTPRequestHandler
import json
import os

COIN = os.environ.get("GAME_COIN", "9uJy4KWMbrxmA5kUtJSJPenZHK5mzd4BzbggNVdRXWh2")
SPL_MINT = os.environ.get("GAME_SPL_MINT", "6tqz6vbw8vaxQtEJC2GvfMZ5ppthvYsyRJQNYPx5pump")
MIN_HOLD_AMOUNT = int(os.environ.get("GAME_MIN_HOLD", "1000"))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({
            "coin": COIN,
            "mint": SPL_MINT,
            "mintResolved": True,
            "minRequired": MIN_HOLD_AMOUNT,
        }).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
