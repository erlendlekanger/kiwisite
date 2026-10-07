"""FOMOCARD, the card brand that sells through this same backend.

Two things live here and nothing else:
  * the virtual card: a wallet claims it once and it stays tied to that wallet.
    It is a picture of a card, not a payment instrument. There is no number to
    hand out, so the only thing stored is who claimed it and when.
  * physical card requests: the delivery details a person types in so a card can
    be posted to them. Kept without expiry, listed for the operator with a key.

Shopping with the virtual card is the checkout in core (core.checkout_*).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import uuid

from op.store import key as kvkey, store

PUBKEY_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHYSICAL_FEE_PCT = 1.0
ADMIN_KEY_ENV = "FOMOCARD_ADMIN_KEY"

# what a delivery needs, and how long each answer may be
FIELDS = {
    "name": 120, "email": 160, "phone": 40,
    "line1": 160, "line2": 160, "city": 80, "region": 80, "postal": 24, "country": 2,
}
REQUIRED = ("name", "email", "line1", "city", "postal", "country")


def _card_view(wallet: str, rec: dict) -> dict:
    # four digits that belong to this wallet and never change: decoration only,
    # so the same card looks the same every time it is opened
    digits = str(int(hashlib.sha256(wallet.encode()).hexdigest(), 16))[-4:]
    return {"wallet": wallet, "claimed_at": rec.get("claimed_at"), "last4": digits,
            "kind": "virtual"}


def card(wallet: str) -> dict:
    wallet = (wallet or "").strip()
    if not PUBKEY_RE.match(wallet):
        return {"ok": False, "error": "not a Solana address"}
    raw = store().cmd("GET", kvkey("card:" + wallet))
    if not raw:
        return {"ok": True, "card": None}
    try:
        return {"ok": True, "card": _card_view(wallet, json.loads(raw))}
    except (TypeError, ValueError):
        return {"ok": True, "card": None}


def claim(payload: dict) -> dict:
    wallet = str(payload.get("wallet") or "").strip()
    if not PUBKEY_RE.match(wallet):
        return {"ok": False, "error": "Connect a Solana wallet first."}
    rec = {"wallet": wallet, "claimed_at": int(time.time())}
    # NX: claiming twice keeps the first date instead of overwriting it
    fresh = store().cmd("SET", kvkey("card:" + wallet), json.dumps(rec), "NX")
    if fresh:
        store().cmd("RPUSH", kvkey("cards"), wallet)
        return {"ok": True, "new": True, "card": _card_view(wallet, rec)}
    return {"ok": True, "new": False, **{k: v for k, v in card(wallet).items() if k != "ok"}}


def request_physical(payload: dict) -> dict:
    data = {}
    for f, most in FIELDS.items():
        v = " ".join(str(payload.get(f) or "").split())
        if len(v) > most:
            return {"ok": False, "error": f"{f} is too long", "field": f}
        data[f] = v
    for f in REQUIRED:
        if not data[f]:
            return {"ok": False, "error": "Please fill in every required field.", "field": f}
    if not EMAIL_RE.match(data["email"]):
        return {"ok": False, "error": "That email address does not look right.", "field": "email"}
    data["country"] = data["country"].upper()
    if not re.match(r"^[A-Z]{2}$", data["country"]):
        return {"ok": False, "error": "Pick a country.", "field": "country"}
    wallet = str(payload.get("wallet") or "").strip()
    rid = uuid.uuid4().hex[:12]
    rec = {"id": rid, **data, "wallet": wallet if PUBKEY_RE.match(wallet) else "",
           "fee_pct": PHYSICAL_FEE_PCT, "status": "requested", "at": int(time.time())}
    store().cmd("SET", kvkey("phys:" + rid), json.dumps(rec))
    store().cmd("RPUSH", kvkey("phys:list"), rid)
    return {"ok": True, "id": rid}


def list_physical(key: str) -> dict:
    want = os.environ.get(ADMIN_KEY_ENV, "").strip()
    if not want or key != want:
        return {"ok": False, "error": "forbidden"}
    ids = store().cmd("LRANGE", kvkey("phys:list"), 0, -1) or []
    out = []
    for rid in ids:
        raw = store().cmd("GET", kvkey("phys:" + str(rid)))
        if raw:
            try:
                out.append(json.loads(raw))
            except (TypeError, ValueError):
                pass
    return {"ok": True, "requests": out}
