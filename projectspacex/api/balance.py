"""Vercel serverless function: GET /api/balance?wallet=<pubkey>

Returns the wallet's $SPACEX balance via Solana RPC. The pump.fun "CA"
(bonding curve) is resolved to its SPL mint; the resolved mint is hardcoded
as the default so each request is fast and avoids extra RPC round-trips.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlparse, parse_qs

# pump.fun coin (bonding-curve CA) shown to users; balances use the SPL mint.
COIN = os.environ.get("GAME_COIN", "9uJy4KWMbrxmA5kUtJSJPenZHK5mzd4BzbggNVdRXWh2")
# Resolved SPL mint for 9uJy...RXWh2 (override via env if the coin changes).
SPL_MINT = os.environ.get("GAME_SPL_MINT", "6tqz6vbw8vaxQtEJC2GvfMZ5ppthvYsyRJQNYPx5pump")
MIN_HOLD_AMOUNT = int(os.environ.get("GAME_MIN_HOLD", "1000"))

DEFAULT_RPCS = (
    "https://api.mainnet-beta.solana.com",
    "https://api.mainnet.solana.com",
)


def _rpc_endpoints():
    custom = os.environ.get("SOLANA_RPC", "").strip()
    out, seen = [], set()
    for url in ([custom] if custom else []) + list(DEFAULT_RPCS):
        if url and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def _rpc(method, params):
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    ).encode("utf-8")
    last_err = "Solana RPC unreachable"
    for url in _rpc_endpoints():
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last_err = f"{url}: {exc}"
            continue
        if data.get("error"):
            msg = str(data["error"].get("message", "RPC error"))
            last_err = f"{url}: {msg}"
            low = msg.lower()
            if ("could not find mint" in low or "could not be unpacked" in low) \
                    and method == "getTokenAccountsByOwner":
                return {"value": []}
            continue
        return data.get("result")
    raise RuntimeError(last_err)


def get_balance(wallet):
    result = _rpc(
        "getTokenAccountsByOwner",
        [wallet, {"mint": SPL_MINT}, {"encoding": "jsonParsed"}],
    )
    value = result.get("value", []) if isinstance(result, dict) else []
    total_raw = 0
    decimals = 6
    for item in value:
        info = (item.get("account", {}).get("data", {})
                .get("parsed", {}).get("info", {}))
        amt = info.get("tokenAmount", {})
        decimals = int(amt.get("decimals", decimals))
        try:
            total_raw += int(amt.get("amount", "0"))
        except (TypeError, ValueError):
            continue
    ui = total_raw / (10 ** decimals) if decimals else float(total_raw)
    return {
        "coin": COIN,
        "mint": SPL_MINT,
        "balance": ui,
        "balanceRaw": str(total_raw),
        "decimals": decimals,
        "minRequired": MIN_HOLD_AMOUNT,
        "meetsMinimum": ui >= MIN_HOLD_AMOUNT,
    }


class handler(BaseHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        wallet = (qs.get("wallet", [""])[0] or "").strip()
        if not wallet:
            self._json(400, {"error": "missing wallet"})
            return
        try:
            self._json(200, get_balance(wallet))
        except RuntimeError as exc:
            self._json(503, {"error": str(exc)})
