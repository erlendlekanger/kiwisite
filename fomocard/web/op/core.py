"""FOMOCARD: routes and checkout logic.

The shape of the product, in one paragraph:

    The shopper picks a card (Uber Eats, Nike, Wolt) and an amount. We ask
    Bitrefill for an invoice payable in USDC on Solana; they hand back an
    address. We build the transactions that pay that address from the shopper's
    own wallet, plus a second transfer of our fee to the treasury. The shopper
    signs once. Nobody's money ever sits with us, so there is no float, no
    ledger of other people's balances and nothing to be licensed for.

    Paying from a memecoin is one extra step: a Jupiter swap, exact-out, for
    the exact USDC the invoice needs. No leftovers, in either direction.

Nothing is broadcast while FOMOCARD_DRY=1 (the default): transactions are
simulated instead and every answer says so.
"""
from __future__ import annotations

import base64
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from solders.compute_budget import set_compute_unit_limit, set_compute_unit_price
from solders.hash import Hash
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.transaction import VersionedTransaction

from op import art, bitrefill, engine, fomocard, redeem
from op.store import is_kv, key as kvkey, store

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
# Every ISO 3166-1 country with a currency, built from the ISO dataset by
# tools/make_countries.py. Bitrefill has no endpoint that lists the countries it
# serves, so the full list is offered and the catalogue itself says which ones
# actually have shops: an empty answer is shown as empty, never as an error.
COUNTRIES = json.loads((ROOT / "countries.json").read_text(encoding="utf-8"))
# Each shop's own background colour, measured from the supplier's artwork by
# tools/make_faces.py. It is only used to lay the logo on a flat field instead of
# a photograph, so every tile in the grid is built the same way.
try:
    FACES = json.loads((ROOT / "faces.json").read_text(encoding="utf-8"))
except OSError:
    FACES = {}
POPULAR = ("US", "GB", "CA", "AU", "DE", "FR", "ES", "IT", "NL", "SE", "NO", "DK", "FI", "PL", "BR", "MX", "JP", "IN", "XI")
DRY = engine.DRY
USDC = str(engine.USDC_MINT)
WSOL = str(engine.WSOL_MINT)
PUBKEY_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
ORDER_TTL_S = 60 * 60 * 24 * 30

# Tokens we always show in the wallet drawer even at a zero balance.
BASE_TOKENS = (WSOL, USDC)


def treasury_wallet() -> str:
    t = (os.environ.get("FOMOCARD_TREASURY") or CONFIG.get("treasury") or "").strip()
    if t and PUBKEY_RE.match(t):
        return t
    kp = engine.load_keypair()
    return str(kp.pubkey()) if kp else ""


def markup_pct() -> float:
    try:
        return float(os.environ.get("FOMOCARD_MARKUP_PCT") or CONFIG["fees"]["markup_pct"])
    except (KeyError, TypeError, ValueError):
        return 4.0


# ---------------------------------------------------------------- catalogue
def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _limit_note(prod: dict) -> str | None:
    notes = CONFIG.get("limits", {}).get("per_account_daily", {})
    slug = _slug(prod.get("name", ""))
    for key, text in notes.items():
        if slug == key or slug.startswith(key + "-") or key in slug.split("-"):
            return text
    return prod.get("_note")


def _live_face(prod: dict) -> dict:
    """The shop's background colour, as the supplier states it, plus whether text
    on it should be dark. No measuring needed when they simply tell us."""
    hexv = (prod.get("logo_background") or "").strip()
    if not (len(hexv) == 7 and hexv.startswith("#")):
        return {}
    try:
        r, g, b = (int(hexv[i:i + 2], 16) for i in (1, 3, 5))
    except ValueError:
        return {}
    return {"face": hexv, "light": (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 > 0.6}


def _card(prod: dict) -> dict:
    """One product, in the shape the page draws."""
    amounts = bitrefill.amounts_for(prod)
    return {
        "id": prod.get("id"),
        "name": prod.get("base_name") or prod.get("name"),
        "country": prod.get("country_code"),
        "country_name": prod.get("country_name"),
        "currency": prod.get("currency"),
        "image": bitrefill.art_url(prod),
        "in_stock": bool(prod.get("in_stock", True)),
        "categories": prod.get("_categories") or prod.get("categories") or [],
        "packages": amounts["packages"],
        "range": amounts["range"],
        "note": _limit_note(prod),
        # how the shop takes it: "account", "checkout", or None when we do not know
        "redeem": prod.get("_redeem") or (prod.get("redemption") or {}).get("mode"),
        # the cleaned mark we hold locally wins over the supplier's raw image: it is
        # trimmed and has no background, so it sits like any icon from our own set
        # the cleaned mark when we hold one; otherwise the page asks for it and the
        # server fetches and trims it on the spot, once, then serves it from disk
        "mark": (f"/assets/shots/{prod.get('id')}.png" if art.have(prod.get("id"))
                 else (f"/api/art?id={prod.get('id')}" if art.WRITABLE else bitrefill.art_url(prod))),
        **(_live_face(prod) or FACES.get(prod.get("id")) or {}),
    }


# The supplier's own category names, tidied for a button. A hardcoded list went
# stale the moment the live catalogue replaced the demo: "retail" and "ecommerce"
# matched nothing at all, because they call those apparel and shopping.
CATEGORY_LABEL = {"food": "Food", "restaurants": "Restaurants", "food-delivery": "Food delivery",
                  "apparel": "Clothing", "entertainment": "Entertainment", "travel": "Travel",
                  "home": "Home", "games": "Games", "experiences": "Experiences",
                  "department-stores": "Department stores", "electronics": "Electronics",
                  "accommodation": "Stays", "shopping": "Shopping", "sports": "Sport",
                  "beauty": "Beauty", "books": "Books", "music": "Music", "pets": "Pets",
                  "kids": "Kids", "groceries": "Groceries", "refill": "Top-ups", "pin": "Top-ups",
                  "payment-cards": "Payment cards", "gaming": "Games", "streaming": "Streaming"}
CATEGORY_HIDE = {"pin", "refill", "gift-cards", "other"}


def categories_for(cards: list[dict], most: int = 8) -> list[dict]:
    """The categories this country actually has, commonest first, so a chip never
    comes back empty."""
    counts: dict[str, int] = {}
    for c in cards:
        for k in c.get("categories") or []:
            if k in CATEGORY_HIDE:
                continue
            counts[k] = counts.get(k, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    out, seen = [], set()
    for key, n in ranked:
        label = CATEGORY_LABEL.get(key, key.replace("-", " ").capitalize())
        if label in seen or n < 3:
            continue
        seen.add(label)
        out.append({"key": key, "label": label, "count": n})
        if len(out) >= most:
            break
    return out


def catalog(country: str, query: str = "", category: str = "") -> dict:
    items, source = bitrefill.catalogue(country or "US")
    cards = [_card(p) for p in items]
    if query:
        q = query.lower().strip()
        cards = [c for c in cards if q in (c["name"] or "").lower()]
    if category:
        cards = [c for c in cards if category in (c.get("categories") or [])]
    # The shortlist is written in the order we want them seen, best known first,
    # and bitrefill.catalogue already returns them that way. Sorting by name here
    # would open the shelf on whatever begins with a digit.
    cards.sort(key=lambda c: (not c["in_stock"],))
    return {"country": (country or "US").upper(), "source": source, "count": len(cards), "cards": cards,
            "categories": categories_for([_card(p) for p in items])}


def find_product(product_id: str, country: str) -> dict | None:
    items, _ = bitrefill.catalogue(country or "US")
    for p in items:
        if p.get("id") == product_id:
            return p
    if bitrefill.configured():
        try:
            return bitrefill.product(product_id) or None
        except bitrefill.BitrefillError:
            return None
    return None


# ---------------------------------------------------------------- wallet
def wallet_tokens(address: str) -> dict:
    """Everything the shopper could pay with, priced. A balance we cannot read
    comes back as None, never as a zero."""
    if not PUBKEY_RE.match(address or ""):
        return {"error": "not a Solana address"}
    holdings: list[dict] = []
    sol = engine.sol_balance(address)
    try:
        res = engine.rpc("getTokenAccountsByOwner", [address, {"programId": str(engine.TOKEN_LEGACY)},
                                                     {"encoding": "jsonParsed", "commitment": "confirmed"}]) or {}
        accounts = res.get("value") or []
    except RuntimeError:
        accounts = []
    try:
        res22 = engine.rpc("getTokenAccountsByOwner", [address, {"programId": str(engine.TOKEN_2022)},
                                                       {"encoding": "jsonParsed", "commitment": "confirmed"}]) or {}
        accounts += res22.get("value") or []
    except RuntimeError:
        pass
    for acc in accounts:
        try:
            info = acc["account"]["data"]["parsed"]["info"]
            amount = info["tokenAmount"]
            raw = int(amount["amount"])
            if raw <= 0:
                continue
            holdings.append({"mint": info["mint"], "raw": raw, "decimals": int(amount["decimals"]),
                             "amount": float(amount["uiAmountString"])})
        except (KeyError, TypeError, ValueError):
            continue
    if sol is not None and sol > 0:
        holdings.insert(0, {"mint": WSOL, "raw": int(sol * engine.LAMPORTS), "decimals": 9, "amount": sol, "native": True})
    mints = [h["mint"] for h in holdings] or list(BASE_TOKENS)
    prices = engine.prices_usd(mints)
    meta = {}
    for m in mints[:30]:
        for t in engine.token_search(m) or []:
            if t.get("id") == m:
                meta[m] = {"symbol": t.get("symbol"), "name": t.get("name"), "icon": t.get("icon")}
                break
    for h in holdings:
        p = prices.get(h["mint"])
        h["price_usd"] = p
        h["value_usd"] = round(h["amount"] * p, 4) if p is not None else None
        h.update(meta.get(h["mint"]) or {})
        if h["mint"] == WSOL:
            h.setdefault("symbol", "SOL")
            h["symbol"] = "SOL"
        if h["mint"] == USDC:
            h["symbol"] = "USDC"
    known = [h for h in holdings if h.get("value_usd") is not None]
    holdings.sort(key=lambda h: -(h.get("value_usd") or 0))
    total = round(sum(h["value_usd"] for h in known), 2) if known else None
    return {"address": address, "sol": sol, "total_usd": total, "priced": len(known),
            "unpriced": len(holdings) - len(known), "tokens": holdings}


# ---------------------------------------------------------------- quoting
def _fee_usd(supplier_usd: float) -> float:
    try:
        floor = float(CONFIG["fees"]["min_fee_usd"])
    except (KeyError, TypeError, ValueError):
        floor = 0.0
    return round(max(supplier_usd * markup_pct() / 100.0, floor), 2)


def quote(product_id: str, country: str, value: float, mint: str = USDC) -> dict:
    """What this costs, before anything is created on Bitrefill's side. The
    supplier figure is theirs (price_rate or a package price), the fee is ours,
    the token figure is a live Jupiter route."""
    prod = find_product(product_id, country)
    if not prod:
        return {"ok": False, "error": "no such product in this country"}
    supplier = bitrefill.price_of(prod, float(value))
    if supplier is None:
        return {"ok": False, "error": "that amount is not available for this shop"}
    currency = prod.get("currency") or "USD"
    fx_source = None
    # price_of already answers in US dollars (satoshis at the BTC price), whatever
    # the card's own currency. Converting a NOK card's figure from NOK again made a
    # 400 NOK Wolt top-up quote at $4.36 instead of about $42.
    supplier_usd = round(supplier, 2)
    fee_usd = _fee_usd(supplier_usd) if supplier_usd is not None else None
    total_usd = round(supplier_usd + fee_usd, 2) if supplier_usd is not None else None
    out: dict = {"ok": True, "product": {"id": prod.get("id"), "name": prod.get("base_name") or prod.get("name"),
                                         "country": prod.get("country_code"), "currency": currency},
                 "face_value": float(value), "supplier": supplier, "supplier_usd": supplier_usd,
                 "fee_usd": fee_usd, "markup_pct": markup_pct(), "total_usd": total_usd,
                 "note": _limit_note(prod), "source": "demo" if not bitrefill.configured() else "live",
                 "fx": {"from": currency, "source": fx_source, "estimated": True} if fx_source else None}
    if total_usd is None:
        out["pay"] = None
        out["error_detail"] = f"no exchange rate for {currency} right now"
        return out
    out["pay"] = _pay_leg(mint, total_usd)
    return out


# Jupiter's free endpoint rate-limits hard, and the amount field fires on every
# keystroke. Asking for a full route each time is what got us throttled, so the
# figure on screen now comes from a cached price and the real exact-out route is
# fetched once, at the moment the shopper actually pays.
_ROUTE_TTL_S = 12
_PRICE_TTL_S = 25
_routes: dict[tuple, tuple[float, dict]] = {}
_prices: dict[str, tuple[float, float | None]] = {}
_routes_lock = threading.RLock()


# Jupiter prices everything, but it throttles. For the two tokens most people pay
# with there are keyless exchange feeds that do not, so those get a second source.
# A memecoin has no such feed; if Jupiter is down for it we say the figure is
# unavailable rather than invent one, and the payment itself is unaffected.
_SPOT = {WSOL: ("https://api.coinbase.com/v2/prices/SOL-USD/spot", ("data", "amount")),
         USDC: ("https://api.coinbase.com/v2/prices/USDC-USD/spot", ("data", "amount"))}


def _spot_price(mint: str) -> float | None:
    src = _SPOT.get(mint)
    if not src:
        return None
    url, path = src
    try:
        d = engine.http_json(url, timeout=10)
        for k in path:
            d = d[k]
        return float(d)
    except (RuntimeError, KeyError, TypeError, ValueError):
        return None


def _cached_price(mint: str) -> float | None:
    now = time.time()
    with _routes_lock:
        hit = _prices.get(mint)
        if hit and now - hit[0] < _PRICE_TTL_S and hit[1] is not None:
            return hit[1]
    px = engine.prices_usd([mint]).get(mint) or _spot_price(mint)
    with _routes_lock:
        _prices[mint] = (now, px)
    return px


def _cached_route(mint: str, raw_usdc: int) -> dict:
    k = (mint, raw_usdc)
    now = time.time()
    with _routes_lock:
        hit = _routes.get(k)
        if hit and now - hit[0] < _ROUTE_TTL_S:
            return hit[1]
    q = engine.jup_quote(mint, USDC, raw_usdc, slippage_bps=int(CONFIG["checkout"]["slippage_bps"]),
                         mode="ExactOut", exclude_dexes=engine.PROP_AMMS)
    with _routes_lock:
        _routes[k] = (now, q)
        if len(_routes) > 400:
            for old_k in [x for x, (t, _) in _routes.items() if now - t > _ROUTE_TTL_S]:
                _routes.pop(old_k, None)
    return q


def _pay_leg(mint: str, total_usd: float) -> dict:
    """How much of `mint` covers total_usd. USDC is one to one. For anything else
    this is an estimate from the token's price, marked as one; the exact-out route
    that decides the real number is built at checkout, where it is needed once."""
    raw_usdc = int(round(total_usd * 1_000_000))
    if mint == USDC:
        return {"mint": USDC, "symbol": "USDC", "amount": total_usd, "raw": raw_usdc, "route": "direct"}
    info = engine.mint_info(mint)
    if not info:
        return {"mint": mint, "error": "unknown mint"}
    dec = int(info["decimals"])
    slip = int(CONFIG["checkout"]["slippage_bps"])

    # a route we already hold is better than a price, so use it when it is fresh
    with _routes_lock:
        hit = _routes.get((mint, raw_usdc))
    if hit and time.time() - hit[0] < _ROUTE_TTL_S:
        q = hit[1]
        raw_in = int(q.get("inAmount") or 0)
        max_in = int(q.get("otherAmountThreshold") or raw_in)
        return {"mint": mint, "amount": raw_in / (10 ** dec), "raw": raw_in,
                "max_amount": max_in / (10 ** dec), "max_raw": max_in, "decimals": dec,
                "route": "jupiter-exact-out", "price_impact_pct": q.get("priceImpactPct"), "slippage_bps": slip}

    px = _cached_price(mint)
    if not px:
        # The figure on screen is missing, not the ability to pay: the real route
        # is built at checkout either way, so this must not read as a failure.
        return {"mint": mint, "decimals": dec, "route": "unpriced", "slippage_bps": slip,
                "unpriced": True}
    amount = total_usd / px
    return {"mint": mint, "amount": amount, "raw": int(round(amount * (10 ** dec))),
            "max_amount": amount * (1 + slip / 10_000), "max_raw": int(round(amount * (1 + slip / 10_000) * (10 ** dec))),
            "decimals": dec, "route": "price-estimate", "price_usd": px, "slippage_bps": slip}


# ---------------------------------------------------------------- invoice
def _invoice_payment(inv: dict, expect_usd: float | None = None) -> dict:
    """The address and the USDC amount from a Bitrefill invoice.

    Their `price` for a usdc_solana invoice is in USDC's smallest unit: a $5.03
    invoice comes back as 5030000. Read as whole dollars that is five million,
    and a transfer built from it would be catastrophic if the wallet could cover
    it. So the unit is applied, and then the figure is checked against what we
    quoted: anything that is not close is refused rather than sent."""
    pay = (inv or {}).get("payment") or {}
    address = pay.get("address") or pay.get("payment_address")
    if not address:
        raise bitrefill.BitrefillError("invoice carries no payment address")

    currency = (pay.get("currency") or "").upper()
    raw = None
    for field in ("crypto_amount", "amount_crypto", "amount", "price", "value"):
        if pay.get(field) not in (None, ""):
            try:
                raw = float(pay[field])
                used = field
                break
            except (TypeError, ValueError):
                continue
    if raw is None:
        raise bitrefill.BitrefillError(f"invoice priced in {currency or 'an unknown currency'}: no amount to read")

    if currency not in ("USDC", "USD"):
        raise bitrefill.BitrefillError(f"invoice is in {currency}, and we only settle USDC")

    # A dollar figure and a base-unit figure are told apart by scale, not by hope:
    # no invoice we create is anywhere near a million dollars, and none is a
    # fraction of a cent, so the two ranges never overlap.
    usdc = raw / 1_000_000 if raw >= 100_000 else raw

    if expect_usd is not None:
        if not (expect_usd * 0.5 <= usdc <= expect_usd * 2 + 1):
            raise bitrefill.BitrefillError(
                f"invoice wants {usdc:.2f} USDC but the quote was {expect_usd:.2f}: refusing to pay it")
    if usdc <= 0 or usdc > 10_000:
        raise bitrefill.BitrefillError(f"invoice amount {usdc} is outside anything we will pay")

    return {"address": address, "usdc": round(usdc, 6), "field": used, "raw": raw,
            "commission": pay.get("commission"), "status": pay.get("status")}


# ---------------------------------------------------------------- checkout
def _save(ref: str, rec: dict) -> None:
    store().cmd("SET", kvkey("order:" + ref), json.dumps(rec, default=str), "EX", ORDER_TTL_S)


def _load(ref: str) -> dict | None:
    raw = store().cmd("GET", kvkey("order:" + ref))
    try:
        return json.loads(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _transfer_leg(payer: str, invoice_addr: str, invoice_usdc: float, fee_usdc: float) -> list:
    """One instruction list: the supplier's USDC, then ours. Two transfers, one
    signature, and both legs are visible on chain for anyone who wants to check."""
    payer_pk = Pubkey.from_string(payer)
    src = engine.ata(payer_pk, engine.USDC_MINT)
    ixs = []
    dests = [(invoice_addr, invoice_usdc)]
    treasury = treasury_wallet()
    if fee_usdc > 0 and treasury:
        dests.append((treasury, fee_usdc))
    for addr, amount in dests:
        owner = Pubkey.from_string(addr)
        dst = engine.ata(owner, engine.USDC_MINT)
        ixs.append(engine.ata_create_idempotent_ix(payer_pk, owner, engine.USDC_MINT))
        ixs.append(engine.transfer_checked_ix(src, engine.USDC_MINT, dst, payer_pk,
                                              int(round(amount * 1_000_000)), 6))
    return ixs


# Measured at 12,384 units when both token accounts already exist, plus about
# 21,000 for each one that has to be created. 75,000 covers the worst case with
# room to spare, and a tighter limit buys a better price per unit for the same fee.
PAY_TX_UNITS = 75_000


def _build_tx(payer: str, ixs: list) -> VersionedTransaction:
    """An unsigned v0 transaction for the browser wallet to sign."""
    bh, _ = engine.blockhash()
    micro = max(1, int(int(CONFIG["checkout"]["priority_lamports"]) * 1_000_000 / PAY_TX_UNITS))
    pre = [set_compute_unit_limit(PAY_TX_UNITS), set_compute_unit_price(micro)]
    msg = MessageV0.try_compile(Pubkey.from_string(payer), pre + list(ixs), [], Hash.from_string(bh))
    return VersionedTransaction.populate(msg, [Signature.default()] * msg.header.num_required_signatures)


def checkout_prepare(payload: dict) -> dict:
    wallet = str(payload.get("wallet") or "").strip()
    product_id = str(payload.get("product_id") or "").strip()
    country = str(payload.get("country") or "US").strip().upper()
    mint = str(payload.get("mint") or USDC).strip()
    email = str(payload.get("email") or "").strip()
    try:
        value = float(payload.get("value"))
    except (TypeError, ValueError):
        return {"ok": False, "error": "no amount"}
    if not PUBKEY_RE.match(wallet):
        return {"ok": False, "error": "connect a wallet first"}
    if mint != USDC and not PUBKEY_RE.match(mint):
        return {"ok": False, "error": "not a token mint"}

    q = quote(product_id, country, value, mint)
    if not q.get("ok"):
        return q
    if q.get("total_usd") is None:
        return {"ok": False, "error": "no exchange rate for " + str(q["product"]["currency"]) + " right now"}
    pay_leg = q.get("pay") or {}
    if pay_leg.get("error") and pay_leg.get("error") != "unknown mint":
        # anything other than a mint we cannot read is a display problem; the
        # exact-out route below is the one that decides whether this can be paid
        pay_leg = {}
    if (q.get("pay") or {}).get("error") == "unknown mint":
        return {"ok": False, "error": "that token could not be read on chain"}

    ref = uuid.uuid4().hex[:16]
    rec: dict = {"ref": ref, "created": int(time.time()), "wallet": wallet, "mint": mint, "country": country,
                 "product_id": product_id, "product_name": q["product"]["name"], "value": value,
                 "quote": q, "status": "prepared", "dry": DRY, "source": q["source"], "invoice": None,
                 "signatures": [], "code": None}

    if not DRY and not storage_ok():
        return {"ok": False, "error": "This site has no order storage configured, so a payment could not be "
                                      "matched to your order. Nothing has been charged."}
    if not DRY and not bitrefill.configured():
        # Live with no supplier means the invoice would be a stand-in address of
        # ours, and the shopper would be sending real money for nothing. Refuse.
        return {"ok": False, "error": "Live mode is on but no supplier is connected, so nothing could be bought. "
                                      "Install the supplier key before taking payments."}
    if DRY:
        # A test must still exercise the real transaction builder, so it pays a
        # stand-in address: the treasury. Flagged, and never sent.
        invoice_addr = treasury_wallet() or wallet
        invoice_usdc = q["supplier_usd"]
        rec["invoice"] = {"id": "test-" + ref, "address": invoice_addr, "usdc": invoice_usdc, "dry": True}
    else:
        inv = bitrefill.invoice_create(product_id, value, CONFIG["checkout"]["payment_method"], email=email)
        pay = _invoice_payment(inv, expect_usd=q["supplier_usd"])
        rec["invoice"] = {"id": inv.get("id"), "address": pay["address"], "usdc": pay["usdc"],
                          "orders": [o.get("id") for o in inv.get("orders") or []], "dry": False}
        invoice_addr, invoice_usdc = pay["address"], pay["usdc"]

    fee_usdc = round(q["fee_usd"], 2)
    txs: list[str] = []
    steps: list[dict] = []
    if mint != USDC:
        raw_usdc = int(round((invoice_usdc + fee_usdc) * 1_000_000))
        try:
            jq = _cached_route(mint, raw_usdc)
        except RuntimeError as exc:
            # A swap we cannot price is a reason to stop, but the shopper should be
            # told what to do about it rather than shown a stack trace.
            msg = str(exc)
            if "rate limit" in msg.lower() or "429" in msg:
                return {"ok": False, "error": "The exchange is busy right now. Wait a few seconds and press pay again, "
                                              "or pay in USDC, which needs no swap.", "retry": True}
            return {"ok": False, "error": "No way to swap that token into USDC right now: " + msg[:140]}
        swap = engine.jup_swap_tx(jq, wallet, priority_lamports=int(CONFIG["checkout"]["priority_lamports"]))
        txs.append(base64.b64encode(bytes(swap)).decode())
        sold = int(jq.get("inAmount") or 0) / (10 ** int(engine.mint_info(mint)["decimals"]))
        steps.append({"kind": "swap", "detail": f"{sold:.6f} -> {invoice_usdc + fee_usdc:.2f} USDC"})
    txs.append(base64.b64encode(bytes(_build_tx(wallet, _transfer_leg(wallet, invoice_addr, invoice_usdc, fee_usdc)))).decode())
    steps.append({"kind": "pay", "detail": f"{invoice_usdc:.2f} USDC to the supplier, {fee_usdc:.2f} USDC fee"})

    rec["fee_usdc"] = fee_usdc
    rec["invoice_usdc"] = invoice_usdc
    rec["steps"] = steps
    _save(ref, rec)
    return {"ok": True, "ref": ref, "txs": txs, "steps": steps, "quote": q, "dry": DRY,
            "invoice_usdc": invoice_usdc, "fee_usdc": fee_usdc,
            "expires": rec["created"] + int(CONFIG["checkout"]["invoice_ttl_s"])}


def checkout_send(payload: dict) -> dict:
    """Signed transactions come back here. In dry mode they are simulated; in live
    mode they are sent in order, because the swap has to land before the pay."""
    ref = str(payload.get("ref") or "")
    signed = payload.get("signed") or []
    rec = _load(ref)
    if not rec:
        return {"ok": False, "error": "unknown order"}
    if rec.get("status") in ("paid", "delivered"):
        return {"ok": True, "ref": ref, "status": rec["status"], "code": rec.get("code")}
    if not isinstance(signed, list) or not signed:
        return {"ok": False, "error": "nothing signed"}

    # A swap in front means the pay transaction spends USDC that does not exist yet:
    # simulated on its own, before the swap has landed, the chain is right to say
    # there are insufficient funds. That is the simulation's limit, not a fault in
    # the payment, so it is reported as unverifiable rather than as a failure. Any
    # other error still stops the run.
    has_swap = any(st.get("kind") == "swap" for st in rec.get("steps") or [])
    def _is_pending_funds(err) -> bool:
        try:
            return err.get("InstructionError", [None, None])[1] == {"Custom": 1}
        except (AttributeError, TypeError, IndexError):
            return False

    results = []
    for i, b64 in enumerate(signed):
        try:
            tx = VersionedTransaction.from_bytes(base64.b64decode(b64))
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "error": f"transaction {i + 1} did not parse: {str(exc)[:120]}"}
        if DRY:
            sim = engine.simulate(tx)
            err = (sim or {}).get("err")
            depends_on_swap = has_swap and i == len(signed) - 1
            pending = bool(err) and depends_on_swap and _is_pending_funds(err)
            results.append({"i": i, "simulated": True, "err": None if pending else err,
                            "pending_on_swap": pending,
                            "units": (sim or {}).get("units"),
                            "logs": ((sim or {}).get("logs") or [])[-4:]})
            if err and not pending:
                rec["status"] = "sim_failed"
                _save(ref, rec)
                return {"ok": False, "error": f"simulation failed on transaction {i + 1}: {str(err)[:160]}",
                        "results": results, "dry": True}
        else:
            sig = engine.send_tx(tx, skip_preflight=False)
            ok = engine.wait_confirmed(sig, timeout=90)
            results.append({"i": i, "signature": sig, "confirmed": ok})
            rec.setdefault("signatures", []).append(sig)
            if not ok:
                rec["status"] = "unconfirmed"
                _save(ref, rec)
                return {"ok": False, "error": f"transaction {i + 1} did not confirm", "results": results}

    rec["status"] = "paid" if not DRY else "simulated"
    rec["results"] = results
    _save(ref, rec)
    if DRY:
        pending = any(x.get("pending_on_swap") for x in results)
        msg = ("Test run finished. The swap simulated cleanly against the live chain. The payment that follows it "
               "could not be simulated on its own, because it spends the USDC the swap has not made yet; that is "
               "expected and it is the only part a test cannot prove. Nothing was sent."
               if pending else
               "Test run finished: every transaction simulated cleanly against the live chain. Nothing was sent.")
        rec["message"] = msg
        _save(ref, rec)
        return {"ok": True, "ref": ref, "status": "simulated", "dry": True, "results": results, "message": msg}
    return {"ok": True, "ref": ref, "status": "paid", "results": results, "code": None}


def order_status(ref: str) -> dict:
    rec = _load(ref)
    if not rec:
        return {"ok": False, "error": "unknown order"}
    out = {"ok": True, "ref": ref, "status": rec.get("status"), "dry": rec.get("dry"),
           "product": rec.get("product_name"), "value": rec.get("value"), "country": rec.get("country"),
           "fee_usdc": rec.get("fee_usdc"), "invoice_usdc": rec.get("invoice_usdc"),
           "signatures": rec.get("signatures") or [], "code": rec.get("code"),
           "message": rec.get("message")}
    # An order bought before this existed still has only the link and the PIN, so
    # the resolve runs on whatever is stored too, not just on a fresh delivery.
    stored = rec.get("code")
    if isinstance(stored, dict) and not stored.get("code"):
        better = redeem.enrich(stored)
        if better and better != stored:
            rec["code"] = better
            _save(ref, rec)
            out["code"] = better

    inv = rec.get("invoice") or {}
    if rec.get("status") == "paid" and inv.get("id") and not inv.get("dry") and not rec.get("code"):
        try:
            live = bitrefill.invoice(inv["id"])
            info = bitrefill.redemption(live)
            out["invoice_status"] = live.get("status")
            if info:
                # Some shops hand back a link and a PIN instead of a card number,
                # and the number the checkout wants is printed on the page behind
                # that link. Read it here so the buyer is given something they can
                # actually type, rather than a puzzle to solve.
                info = redeem.enrich(info) or info
                rec["code"] = info
                rec["status"] = "delivered"
                _save(ref, rec)
                out["code"] = info
                out["status"] = "delivered"
        except bitrefill.BitrefillError as exc:
            out["supplier_error"] = str(exc)[:200]
    return out


# ---------------------------------------------------------------- misc
def countries() -> list[dict]:
    """The whole world, with the ones people actually pick floated to the top."""
    rank = {c: i for i, c in enumerate(POPULAR)}
    return sorted(COUNTRIES, key=lambda c: (rank.get(c["code"], 999), c["name"]))


def public_config() -> dict:
    return {"brand": CONFIG["brand"], "tagline": CONFIG["tagline"], "countries": countries(),
            "token_mint": (CONFIG.get("token") or {}).get("mint") or "",
            "popular": list(POPULAR),
            "categories": CONFIG["categories"], "markup_pct": markup_pct(),
            "treasury": treasury_wallet(), "dry": DRY, "supplier": "bitrefill",
            "supplier_live": bitrefill.configured(), "usdc": USDC,
            "live_sales": can_sell()[0], "blocked_by": can_sell()[1] or None,
            "physical_price_sol": fomocard.physical_price_sol()}


def storage_ok() -> bool:
    """An order is written when it is prepared and read back when it is paid. On a
    host where each request is its own machine, a file is not storage: without a
    shared store the second half of a purchase would never find the first."""
    if is_kv():
        return True
    return os.environ.get("VERCEL") is None      # a local file is fine locally


def can_sell() -> tuple[bool, str]:
    """Whether a real purchase is possible at all, and what is missing if not."""
    if not bitrefill.configured():
        return False, "no supplier key installed (" + bitrefill.KEY_FILE + ")"
    if not treasury_wallet():
        return False, "no treasury set (FOMOCARD_TREASURY or ~/fomocard_key.txt)"
    if not storage_ok():
        return False, "no shared store configured, so an order could not be read back after payment"
    if DRY:
        return False, "test mode is on (set FOMOCARD_DRY=0)"
    return True, ""


def health() -> dict:
    ok, why = can_sell()
    out = {"ok": True, "dry": DRY, "live_sales": ok, "blocked_by": why or None,
           "treasury": treasury_wallet() or None, "supplier": bitrefill.health()}
    try:
        out["rpc_block"] = engine.block_height()
    except RuntimeError as exc:
        out["ok"] = False
        out["rpc_error"] = str(exc)[:160]
    try:
        engine.jup_quote(WSOL, USDC, 1_000_000_000, mode="ExactIn")
        out["jupiter"] = "ok"
    except RuntimeError as exc:
        out["jupiter"] = str(exc)[:160]
    return out


# ---------------------------------------------------------------- dispatcher
def dispatch(method: str, path: str, query: dict, headers, body: bytes | None):
    def J(obj, code=200, cache="no-store"):
        return code, "application/json; charset=utf-8", json.dumps(obj, allow_nan=False, default=str).encode("utf-8"), {"Cache-Control": cache}

    qp = lambda k: str((query.get(k) or [""])[0])  # noqa: E731

    if method == "OPTIONS":
        return 204, "text/plain", b"", {"Allow": "GET, POST, OPTIONS"}

    if method == "GET":
        if path == "/api/config":
            return J(public_config())
        if path == "/api/catalog":
            return J(catalog(qp("country") or "US", qp("q"), qp("category")), cache="public, max-age=120")
        if path == "/api/quote":
            try:
                v = float(qp("value"))
            except ValueError:
                return J({"ok": False, "error": "no amount"}, 400)
            d = quote(qp("id"), qp("country") or "US", v, qp("mint") or USDC)
            return J(d, 200 if d.get("ok") else 400)
        if path == "/api/wallet":
            return J(wallet_tokens(qp("address")))
        if path == "/api/order":
            d = order_status(qp("ref"))
            return J(d, 200 if d.get("ok") else 404)
        if path == "/api/art":
            # a shop we have not cleaned yet: fetch, trim and cache it now
            f = art.mark(qp("id"))
            if not f:
                return 404, "text/plain", b"no artwork", {"Cache-Control": "public, max-age=3600"}
            return 200, "image/png", f.read_bytes(), {"Cache-Control": "public, max-age=86400"}
        if path == "/api/health":
            return J(health())
        if path == "/api/fomocard/card":
            d = fomocard.card(qp("wallet"))
            return J(d, 200 if d.get("ok") else 400)
        if path == "/api/fomocard/requests":
            d = fomocard.list_physical(qp("key"))
            return J(d, 200 if d.get("ok") else 403)
        return J({"error": "not found"}, 404)

    if method == "POST":
        try:
            payload = json.loads((body or b"{}").decode("utf-8") or "{}")
        except ValueError:
            return J({"ok": False, "error": "bad json"}, 400)
        if not isinstance(payload, dict):
            return J({"ok": False, "error": "bad json"}, 400)
        if path == "/api/checkout/prepare":
            d = checkout_prepare(payload)
            return J(d, 200 if d.get("ok") else 400)
        if path == "/api/checkout/send":
            d = checkout_send(payload)
            return J(d, 200 if d.get("ok") else 400)
        if path == "/api/fomocard/claim":
            d = fomocard.claim(payload)
            return J(d, 200 if d.get("ok") else 400)
        if path == "/api/fomocard/physical/prepare":
            d = fomocard.physical_prepare(payload)
            return J(d, 200 if d.get("ok") else 400)
        if path == "/api/fomocard/physical/send":
            d = fomocard.physical_send(payload)
            return J(d, 200 if d.get("ok") else 400)
        return J({"error": "not found"}, 404)

    return J({"error": "method not allowed"}, 405)
