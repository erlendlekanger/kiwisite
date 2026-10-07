"""FOMOCARD, the card brand that sells through this same backend.

Two things live here and nothing else:
  * the virtual card: a wallet claims it once and it stays tied to that wallet.
    It is a picture of a card, not a payment instrument. There is no number to
    hand out, so the only thing stored is who claimed it and when.
  * physical card orders: the delivery details a person types in so a card can
    be posted to them, paid for with PHYSICAL_PRICE_SOL to the treasury before the
    order exists. Kept without expiry, listed for the operator with a key.

Shopping with the virtual card is the checkout in core (core.checkout_*).
"""
from __future__ import annotations

import base64
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
PHYSICAL_PRICE_SOL = 0.1          # what ordering the physical card costs, paid to the treasury
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


def _delivery(payload: dict) -> tuple[dict | None, dict | None]:
    """The delivery details, cleaned, or the first problem with them."""
    data = {}
    for f, most in FIELDS.items():
        v = " ".join(str(payload.get(f) or "").split())
        if len(v) > most:
            return None, {"ok": False, "error": f"{f} is too long", "field": f}
        data[f] = v
    for f in REQUIRED:
        if not data[f]:
            return None, {"ok": False, "error": "Please fill in every required field.", "field": f}
    if not EMAIL_RE.match(data["email"]):
        return None, {"ok": False, "error": "That email address does not look right.", "field": "email"}
    data["country"] = data["country"].upper()
    if not re.match(r"^[A-Z]{2}$", data["country"]):
        return None, {"ok": False, "error": "Pick a country.", "field": "country"}
    return data, None


def physical_price_sol() -> float:
    return float(os.environ.get("FOMOCARD_PHYSICAL_PRICE_SOL") or PHYSICAL_PRICE_SOL)


def physical_prepare(payload: dict) -> dict:
    """Step one of an order: the details are checked and kept aside, and the
    wallet gets one unsigned transaction paying the order price to the treasury.
    Nothing is recorded as an order until that payment has landed."""
    from op import core, engine  # core imports this module, so not at the top
    from solders.pubkey import Pubkey

    data, err = _delivery(payload)
    if err:
        return err
    wallet = str(payload.get("wallet") or "").strip()
    if not PUBKEY_RE.match(wallet):
        return {"ok": False, "error": "Connect your wallet to pay for the card."}
    treasury = core.treasury_wallet()
    if not treasury:
        return {"ok": False, "error": "Card orders are not open right now."}
    lamports = int(round(physical_price_sol() * 1_000_000_000))
    tx = core._build_tx(wallet, [engine.system_transfer_ix(Pubkey.from_string(wallet), Pubkey.from_string(treasury), lamports)])
    rid = uuid.uuid4().hex[:12]
    pending = {"id": rid, **data, "wallet": wallet, "price_sol": physical_price_sol(), "lamports": lamports,
               "treasury": treasury, "message": base64.b64encode(bytes(tx.message)).decode(), "at": int(time.time())}
    store().cmd("SET", kvkey("phys_pending:" + rid), json.dumps(pending), "EX", 3600)
    return {"ok": True, "id": rid, "price_sol": physical_price_sol(), "tx": base64.b64encode(bytes(tx)).decode()}


def physical_send(payload: dict) -> dict:
    """Step two: the signed payment comes back. It must be exactly the transaction
    we built (same payer, recipient and amount), it is sent, and only once the
    chain confirms it does the order exist."""
    from op import core, engine
    from solders.transaction import VersionedTransaction

    rid = str(payload.get("id") or "")
    done = store().cmd("GET", kvkey("phys:" + rid))
    if done:
        return {"ok": True, "id": rid, "status": "requested"}
    raw = store().cmd("GET", kvkey("phys_pending:" + rid))
    if not raw:
        return {"ok": False, "error": "This order expired. Please fill in the form again."}
    pending = json.loads(raw)
    try:
        tx = VersionedTransaction.from_bytes(base64.b64decode(str(payload.get("signed") or "")))
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "The signed payment could not be read."}
    if base64.b64encode(bytes(tx.message)).decode() != pending["message"]:
        return {"ok": False, "error": "The signed payment does not match the order."}
    if core.DRY:
        sim = engine.simulate(tx)
        if (sim or {}).get("err"):
            return {"ok": False, "error": "The payment would fail. Check that the wallet holds enough SOL."}
        sig, status = "simulated", "simulated"
    else:
        try:
            sig = engine.send_tx(tx, skip_preflight=False)
        except Exception as exc:  # noqa: BLE001
            low = str(exc).lower()
            if "insufficient" in low or "0x1" in low:
                return {"ok": False, "error": f"Not enough SOL. The card costs {pending['price_sol']} SOL plus a small network fee."}
            return {"ok": False, "error": "The payment could not be sent. Nothing was charged, please try again."}
        if not engine.wait_confirmed(sig, timeout=45):
            store().cmd("SET", kvkey("phys_unconfirmed:" + rid), json.dumps({**pending, "signature": sig}), "EX", 7 * 86400)
            return {"ok": False, "error": "The payment was sent but has not confirmed yet. If it confirms, contact us with request " + rid + "."}
        status = "requested"
    rec = {k: v for k, v in pending.items() if k != "message"}
    rec.update({"signature": sig, "fee_pct": PHYSICAL_FEE_PCT, "status": status, "paid_at": int(time.time())})
    store().cmd("SET", kvkey("phys:" + rid), json.dumps(rec))
    store().cmd("RPUSH", kvkey("phys:list"), rid)
    store().cmd("DEL", kvkey("phys_pending:" + rid))
    return {"ok": True, "id": rid, "status": status, "signature": sig}


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
