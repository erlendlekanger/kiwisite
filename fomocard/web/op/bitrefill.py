"""FOMOCARD: the Bitrefill v2 client.

Bitrefill is the supplier. We send them crypto, they hand back a gift card code.
Everything here is either a real call to https://api-bitrefill.com/v2 or, when no
key is installed, a clearly flagged demo catalogue so the site can be built and
tested without spending a cent. A demo answer always carries source="demo";
nothing in this file ever presents made-up numbers as real ones.

Key (either form) in ~/fomocard_bitrefill.txt or env FOMOCARD_BITREFILL_KEY:
    <api_id>:<api_secret>      -> HTTP Basic (what the dashboard hands out)
    <token>                    -> Bearer

Docs: docs.bitrefill.com  (core-concepts, crypto-payments, reference/*)
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("FOMOCARD_BITREFILL_API", "https://api-bitrefill.com/v2").rstrip("/")

# The supplier's US shelf runs past 600 products and opens on "1-800-Baskets.com".
# A wall of names nobody recognises is worse than a short list of ones they do, so
# the catalogue is filtered to a curated set of product ids, checked against the
# live shelf. Prices, ranges and availability still come from them, every time:
# this only decides which shops are shown. Set FOMOCARD_ALL_SHOPS=1 to see everything.
SHORTLIST: dict[str, list[str]] = {}
try:
    SHORTLIST = json.loads((Path(__file__).resolve().parent / "shortlist.json").read_text(encoding="utf-8"))
except (OSError, ValueError):
    SHORTLIST = {}
SHOW_ALL = os.environ.get("FOMOCARD_ALL_SHOPS", "").strip() in ("1", "true", "yes")
KEY_FILE = os.path.expanduser(os.environ.get("FOMOCARD_BITREFILL_KEY_FILE", "~/fomocard_bitrefill.txt"))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FOMOCARD/1.0"}

# Payment methods we are willing to quote. Bitrefill's full list is in their
# crypto-payments doc; these are the Solana ones plus the balance rail.
SOLANA_METHODS = ("usdc_solana", "solana")

_lock = threading.RLock()
_cache: dict[str, tuple[float, object]] = {}


class BitrefillError(RuntimeError):
    pass


# ------------------------------------------------------------------ auth
def _key() -> str:
    """The key, and nothing else. The file is allowed to carry # comments and
    blank lines, the way the wallet key file does, so they are skipped here:
    reading the whole file and handing it to a header is how the first attempt
    failed. utf-8-sig because Notepad writes a BOM."""
    k = (os.environ.get("FOMOCARD_BITREFILL_KEY") or "").strip()
    if k:
        return k
    try:
        for line in Path(KEY_FILE).read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                return line
    except OSError:
        pass
    return ""


def configured() -> bool:
    return bool(_key())


def _auth_header() -> dict:
    k = _key()
    if not k:
        raise BitrefillError("no Bitrefill key: put <api_id>:<api_secret> in " + KEY_FILE)
    if ":" in k:
        return {"Authorization": "Basic " + base64.b64encode(k.encode()).decode()}
    return {"Authorization": "Bearer " + k}


# ------------------------------------------------------------------ http
def _req(method: str, path: str, params: dict | None = None, body: dict | None = None, timeout: int = 25):
    url = API + path + ("?" + urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v not in (None, "")}) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    headers = {**UA, **_auth_header()}
    if data:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "ignore")[:300]
        raise BitrefillError(f"{method} {path} -> {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise BitrefillError(f"{method} {path} -> {exc}") from exc
    if isinstance(payload, dict) and payload.get("error"):
        raise BitrefillError(str(payload["error"])[:300])
    # Every v2 answer is {meta, data}; hand back data and let callers keep meta out of it.
    return payload.get("data") if isinstance(payload, dict) and "data" in payload else payload


# ------------------------------------------------------------------ catalogue
def products(country: str = "US", category: str = "", limit: int = 50, start: int = 0, test: bool = False) -> list[dict]:
    """Raw product list for one country. ISO 3166-1 alpha-2, "XI" = international."""
    out = _req("GET", "/products", {"country": country.upper(), "category": category, "limit": min(int(limit), 50),
                                    "start": int(start), "include_test_products": "true" if test else None})
    return out if isinstance(out, list) else (out or {}).get("products") or []


def product(product_id: str) -> dict:
    return _req("GET", "/products/" + urllib.parse.quote(product_id)) or {}


def search(query: str, country: str = "US") -> list[dict]:
    out = _req("GET", "/products/search", {"query": query, "country": country.upper()})
    return out if isinstance(out, list) else (out or {}).get("products") or []


# ------------------------------------------------------------------ buying
def invoice_create(product_id: str, value: float, payment_method: str = "usdc_solana", quantity: int = 1,
                   email: str = "", webhook_url: str = "") -> dict:
    """Create an invoice for one product. The answer carries the payment address
    the buyer must send to, and one order per line item."""
    if payment_method not in SOLANA_METHODS and payment_method != "balance":
        raise BitrefillError(f"payment method {payment_method!r} is not one we quote")
    item: dict = {"product_id": product_id, "quantity": int(quantity), "value": value}
    body: dict = {"products": [item], "payment_method": payment_method}
    if email:
        body["gift"] = {"recipient_email": email, "recipient_name": "FOMOCARD customer", "sender_name": "FOMOCARD"}
    if webhook_url:
        body["webhook_url"] = webhook_url
    return _req("POST", "/invoices", body=body) or {}


def invoice(invoice_id: str) -> dict:
    return _req("GET", "/invoices/" + urllib.parse.quote(invoice_id)) or {}


def order(order_id: str) -> dict:
    return _req("GET", "/orders/" + urllib.parse.quote(order_id)) or {}


def balance() -> dict:
    """Business accounts only; Personal keys get an error, which is information too."""
    return _req("GET", "/accounts/balance") or {}


def redemption(inv: dict) -> dict | None:
    """The code, once an order is delivered. Shape differs per product, so hand
    back whatever Bitrefill gave and let the page show the fields it knows."""
    for o in (inv or {}).get("orders") or []:
        info = o.get("redemption_info") or o.get("redemptionInfo")
        if info:
            return info
    return None


# ------------------------------------------------------------------ pricing
# Bitrefill quotes every price in satoshis, whatever the card's own currency is:
# a $50 Airbnb package comes back as 61909, and `range.price_rate` is satoshis per
# unit of face value. Read as dollars that is a $61,909 gift card, so the rate has
# to be undone before anything is shown to anyone. Satoshis are currency-neutral,
# so one BTC price converts every product in the catalogue.
SATS = 100_000_000
_btc_lock = threading.RLock()
_btc: tuple[float, float] | None = None
BTC_TTL_S = 120


def btc_usd() -> float | None:
    """Keyless, and cached: the catalogue is priced against it on every quote."""
    global _btc
    with _btc_lock:
        if _btc and time.time() - _btc[0] < BTC_TTL_S:
            return _btc[1]
    for url, path in (("https://api.coinbase.com/v2/prices/BTC-USD/spot", ("data", "amount")),
                      ("https://api.kraken.com/0/public/Ticker?pair=XBTUSD", None)):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=10) as r:
                d = json.loads(r.read().decode("utf-8"))
            if path:
                for k in path:
                    d = d[k]
                px = float(d)
            else:
                px = float(next(iter(d["result"].values()))["c"][0])
            if px > 0:
                with _btc_lock:
                    _btc = (time.time(), px)
                return px
        except Exception:  # noqa: BLE001
            continue
    return None


def sats_to_usd(sats: float) -> float | None:
    px = btc_usd()
    return None if px is None else round(float(sats) / SATS * px, 2)


def price_of(prod: dict, value: float) -> float | None:
    """What WE pay for `value` worth of this card, **in US dollars**.

    A fixed package carries its own satoshi price, which is what we actually owe.
    A free-amount purchase is charged at `range.price_rate` satoshis per unit.
    None when the product cannot be bought at that value, or when no BTC price
    can be read, because a made-up figure here would be a made-up price."""
    for p in prod.get("packages") or []:
        try:
            if abs(float(p.get("value")) - float(value)) < 1e-9 and p.get("price") is not None:
                return sats_to_usd(float(p["price"]))
        except (TypeError, ValueError):
            continue
    rng = prod.get("range") or {}
    try:
        lo, hi = float(rng["min"]), float(rng["max"])
        rate = float(rng["price_rate"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (lo - 1e-9 <= float(value) <= hi + 1e-9):
        return None
    return sats_to_usd(float(value) * rate)


def amounts_for(prod: dict) -> dict:
    """What the page needs to draw an amount picker. Values are face value in the
    card's own currency; the satoshi prices are not shown to anyone."""
    packages = []
    for p in prod.get("packages") or []:
        try:
            packages.append({"value": float(p["value"]), "id": p.get("id")})
        except (KeyError, TypeError, ValueError):
            continue
    rng = prod.get("range") or {}
    out: dict = {"packages": sorted(packages, key=lambda x: x["value"]), "range": None}
    try:
        out["range"] = {"min": float(rng["min"]), "max": float(rng["max"]), "step": float(rng.get("step") or 0.01)}
    except (KeyError, TypeError, ValueError):
        out["range"] = None
    return out


def buyable(prod: dict) -> bool:
    """We collect an amount and a wallet, nothing else. A product that needs a
    phone number or an account id is not something we can order, so it is kept
    out of the catalogue rather than failing at checkout."""
    if (prod.get("recipient_type") or "none") != "none":
        return False
    return bool(prod.get("in_stock", True)) and bool(prod.get("packages") or prod.get("range"))


# ------------------------------------------------------------------ demo mode
# Used only when no key is installed. Shapes copied from the documented schema so
# the page and the tests exercise the real code path. Marked demo everywhere.
# a stand-in satoshi rate, so the demo prices look like live ones
DEMO_SATS_PER_UNIT = 1232.0
_DEMO: dict[str, list[dict]] = {}


def _demo(pid, name, cc, cname, cur, cats, packs, lo, hi, step, note=None, redeem=None):
    """`redeem` is how the shop takes it, and it is only set where we have actually
    seen it, because the two are not interchangeable:

      "account"   the balance goes onto your account first and then comes off
                  every order by itself (Uber Cash works this way).
      "checkout"  there is a field at the payment step and you put it in there,
                  order by order (Nike's US checkout works this way).

    Left unset it stays unset. Guessing would send someone hunting for a field
    that is not there, which is the one thing this has to get right."""
    # The demo has to have the same shape as the live answer or the two take
    # different code paths and only one of them is ever really tested. Live prices
    # are satoshis, and price_rate is satoshis per unit of face value, so the demo
    # is built that way too, against a fixed stand-in rate.
    return {"id": pid, "name": name, "base_name": name, "country_code": cc, "country_name": cname, "currency": cur,
            "recipient_type": "none", "in_stock": True, "_categories": cats,
            "packages": [{"id": f"{pid}<&>{int(v)}", "value": str(int(v)),
                          "price": round(float(v) * DEMO_SATS_PER_UNIT)} for v in packs],
            "range": {"min": float(lo), "max": float(hi), "step": float(step), "price_rate": DEMO_SATS_PER_UNIT},
            **({"_note": note} if note else {}), **({"_redeem": redeem} if redeem else {})}


# Which shops appear in which country is NOT ours to invent: a top-up only works
# where that shop actually redeems one, and listing a shop that does not is how a
# customer ends up at a checkout with nowhere to put it. The brand lists below are
# the ones Bitrefill publishes for each country (checked 2026-09-20). Nike, for
# one, is sold for the United States and not for Norway, which is exactly the kind
# of thing that has to be right. The amounts are stand-ins until the live
# catalogue is connected, and the page says so.
_UBER_NOTE = "Uber allows one top-up per day, per Uber account."

# Bitrefill serves a ready-made brand image per product from an open CDN, keyed by
# the product's own id. That is where every logo below comes from: the shop's own
# artwork by way of the supplier, not anything we drew. Each id was checked against
# that CDN on 2026-09-20, so none of these is a guess.
IMG = "https://cdn.bitrefill.com/primg/w250h100i1/{pid}.webp"


def art_url(prod: dict, size: str = "w1000h400i1") -> str:
    """The shop's own artwork, keyed by the product id. Not by the product's
    `image` field: on a live product that is an internal path such as
    "2024_logos/airbnb_logo", and the public CDN answers 404 for it."""
    pid = prod.get("id")
    return f"https://cdn.bitrefill.com/primg/{size}/{pid}.webp" if pid else ""


def _d(pid, name, cc, cname, cur, cats, packs, lo, hi, step, note=None, redeem=None):
    d = _demo(pid, name, cc, cname, cur, cats, packs, lo, hi, step, note, redeem)
    d["image"] = IMG.format(pid=pid)
    return d


_DEMO["US"] = [
    _d('uber-eats-usa', 'Uber Eats', 'US', 'United States', 'USD', ['food-delivery'], [20.0, 50.0, 100.0], 5.0, 500.0, 0.01, _UBER_NOTE, "account"),
    _d('doordash-usa', 'DoorDash', 'US', 'United States', 'USD', ['food-delivery'], [25.0, 50.0, 100.0], 5.0, 500.0, 0.01),
    _d('nike-usa', 'Nike', 'US', 'United States', 'USD', ['retail'], [25.0, 60.0, 120.0], 10.0, 240.0, 1.0, None, "checkout"),
    _d('amazon-usa', 'Amazon', 'US', 'United States', 'USD', ['ecommerce'], [25.0, 50.0, 100.0], 1.0, 2000.0, 0.01, None, "account"),
    _d('apple-usa', 'Apple', 'US', 'United States', 'USD', ['ecommerce'], [25.0, 50.0, 100.0], 2.0, 500.0, 1.0),
    _d('airbnb-usa', 'Airbnb', 'US', 'United States', 'USD', ['travel'], [50.0, 100.0, 200.0], 25.0, 500.0, 1.0),
    _d('spotify-usa', 'Spotify', 'US', 'United States', 'USD', ['entertainment'], [10.0, 30.0, 60.0], 10.0, 60.0, 10.0),
    _d('netflix-usa', 'Netflix', 'US', 'United States', 'USD', ['entertainment'], [25.0, 50.0, 100.0], 25.0, 100.0, 25.0),
    _d('steam-usa', 'Steam', 'US', 'United States', 'USD', ['games'], [20.0, 50.0, 100.0], 5.0, 100.0, 5.0, None, "account"),
    _d('blizzard-usa', 'Blizzard', 'US', 'United States', 'USD', ['games'], [20.0, 50.0], 5.0, 50.0, 5.0),
    _d('gamestop-usa', 'GameStop', 'US', 'United States', 'USD', ['games'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('starbucks-usa', 'Starbucks', 'US', 'United States', 'USD', ['food-delivery'], [10.0, 25.0, 50.0], 5.0, 500.0, 1.0),
    _d('target-usa', 'Target', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('walmart-usa', 'Walmart', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('best-buy-usa', 'Best Buy', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('home-depot-usa', 'The Home Depot', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('lowes-usa', 'Lowe’s', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('macys-usa', 'Macy’s', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('nordstrom-usa', 'Nordstrom', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('sephora-usa', 'Sephora', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('ulta-beauty-usa', 'Ulta Beauty', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('gap-usa', 'Gap', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('old-navy-usa', 'Old Navy', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('adidas-usa', 'Adidas', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('foot-locker-usa', 'Foot Locker', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 250.0, 1.0),
    _d('famous-footwear-usa', 'Famous Footwear', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 10.0, 250.0, 1.0),
    _d('fanatics-usa', 'Fanatics', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('columbia-sportswear-usa', 'Columbia Sportswear', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('bass-pro-shops-usa', 'Bass Pro Shops', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('bath-and-body-works-usa', 'Bath & Body Works', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('barnes-and-noble-usa', 'Barnes & Noble', 'US', 'United States', 'USD', ['retail'], [10.0, 25.0, 50.0], 3.0, 500.0, 1.0),
    _d('burlington-usa', 'Burlington', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 10.0, 250.0, 1.0),
    _d('autozone-usa', 'AutoZone', 'US', 'United States', 'USD', ['retail'], [25.0, 50.0, 100.0], 10.0, 500.0, 1.0),
    _d('groupon-usa', 'Groupon', 'US', 'United States', 'USD', ['ecommerce'], [25.0, 50.0, 100.0], 10.0, 200.0, 1.0),
    _d('atandt-usa', 'AT&T', 'US', 'United States', 'USD', ['ecommerce'], [25.0, 50.0, 100.0], 10.0, 228.0, 1.0),
    _d('fandango-usa', 'Fandango', 'US', 'United States', 'USD', ['entertainment'], [25.0, 50.0, 100.0], 25.0, 100.0, 25.0),
    _d('amc-theatres-usa', 'AMC Theatres', 'US', 'United States', 'USD', ['entertainment'], [25.0, 50.0, 100.0], 3.0, 200.0, 1.0),
    _d('applebees-usa', 'Applebee’s', 'US', 'United States', 'USD', ['food-delivery'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('california-pizza-kitchen', 'California Pizza Kitchen', 'US', 'United States', 'USD', ['food-delivery'], [25.0, 50.0, 100.0], 20.0, 500.0, 1.0),
    _d('baskin-robbins-usa', 'Baskin Robbins', 'US', 'United States', 'USD', ['food-delivery'], [10.0, 25.0, 50.0], 5.0, 100.0, 1.0),
    _d('cracker-barrel-usa', 'Cracker Barrel', 'US', 'United States', 'USD', ['food-delivery'], [25.0, 50.0, 100.0], 25.0, 100.0, 25.0),
    _d('lyft-usa', 'Lyft', 'US', 'United States', 'USD', ['travel'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('delta-air-lines-usa', 'Delta Air Lines', 'US', 'United States', 'USD', ['travel'], [100.0, 250.0, 500.0], 50.0, 1000.0, 25.0),
    _d('southwest-airlines-usa', 'Southwest Airlines', 'US', 'United States', 'USD', ['travel'], [100.0, 250.0, 500.0], 50.0, 1000.0, 25.0),
]
_DEMO["NO"] = [
    _d('wolt-norway', 'Wolt', 'NO', 'Norway', 'NOK', ['food-delivery'], [150.0, 500.0, 1000.0], 150.0, 1500.0, 10.0),
    _d('foodora-norway', 'foodora', 'NO', 'Norway', 'NOK', ['food-delivery'], [100.0, 200.0, 300.0], 100.0, 300.0, 50.0),
    _d('hellofresh-norway', 'HelloFresh', 'NO', 'Norway', 'NOK', ['food-delivery'], [100.0, 500.0, 1200.0], 100.0, 1200.0, 100.0),
    _d('zalando-norway', 'Zalando', 'NO', 'Norway', 'NOK', ['retail'], [250.0, 500.0, 1000.0], 100.0, 2000.0, 50.0),
    _d('adidas-norway', 'Adidas', 'NO', 'Norway', 'NOK', ['retail'], [250.0, 500.0, 1000.0], 100.0, 2000.0, 50.0),
    _d('ikea-norway', 'IKEA', 'NO', 'Norway', 'NOK', ['retail'], [250.0, 500.0, 1000.0], 100.0, 5000.0, 50.0),
]
_DEMO["GB"] = [
    _d('uber-eats-uk', 'Uber Eats', 'GB', 'United Kingdom', 'GBP', ['food-delivery'], [15.0, 25.0, 50.0], 10.0, 300.0, 1.0, _UBER_NOTE, "account"),
    _d('deliveroo-uk', 'Deliveroo', 'GB', 'United Kingdom', 'GBP', ['food-delivery'], [15.0, 25.0, 50.0], 10.0, 200.0, 1.0),
    _d('nike-uk', 'Nike', 'GB', 'United Kingdom', 'GBP', ['retail'], [25.0, 50.0, 100.0], 10.0, 250.0, 1.0, None, "checkout"),
    _d('adidas-uk', 'Adidas', 'GB', 'United Kingdom', 'GBP', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('amazon-uk', 'Amazon', 'GB', 'United Kingdom', 'GBP', ['ecommerce'], [25.0, 50.0, 100.0], 1.0, 500.0, 1.0, None, "account"),
    _d('asos-uk', 'ASOS', 'GB', 'United Kingdom', 'GBP', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('argos-uk', 'Argos', 'GB', 'United Kingdom', 'GBP', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('tesco-uk', 'Tesco', 'GB', 'United Kingdom', 'GBP', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('primark-uk', 'Primark', 'GB', 'United Kingdom', 'GBP', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('currys-uk', 'Currys', 'GB', 'United Kingdom', 'GBP', ['retail'], [25.0, 50.0, 100.0], 5.0, 500.0, 1.0),
    _d('netflix-uk', 'Netflix', 'GB', 'United Kingdom', 'GBP', ['entertainment'], [25.0, 50.0], 25.0, 100.0, 25.0),
    _d('spotify-uk', 'Spotify', 'GB', 'United Kingdom', 'GBP', ['entertainment'], [10.0, 30.0, 60.0], 10.0, 60.0, 10.0),
]


def demo_products(country: str = "US") -> list[dict]:
    return [dict(p) for p in _DEMO.get(country.upper(), [])]


def demo_countries() -> list[str]:
    return sorted(_DEMO)


# ------------------------------------------------------------------ cached facade
def catalogue(country: str = "US", ttl: int = 600) -> tuple[list[dict], str]:
    """(products, source). source is "live" or "demo"; callers must pass it on so
    the page can say which one the visitor is looking at."""
    country = (country or "US").upper()
    if not configured():
        return demo_products(country), "demo"
    key = "cat:" + country
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return list(hit[1]), "live"  # type: ignore[arg-type]
    items: list[dict] = []
    start = 0
    while start < 600:                      # the US list runs well past 200
        try:
            page = products(country=country, limit=50, start=start)
        except BitrefillError as exc:
            # A country they do not serve answers 400. That is an empty shelf, not
            # a broken site, and the page says so; anything else is a real fault.
            if "invalid_param" in str(exc) or "Invalid country" in str(exc):
                return [], "live"
            raise
        items.extend(page)
        if len(page) < 50:
            break
        start += 50
    items = [p for p in items if buyable(p)]
    keep = SHORTLIST.get(country)
    if keep and not SHOW_ALL:
        order = {pid: i for i, pid in enumerate(keep)}
        items = sorted((p for p in items if p["id"] in order), key=lambda p: order[p["id"]])
    with _lock:
        _cache[key] = (time.time(), items)
    return items, "live"


def health() -> dict:
    """What is and is not wired up. Never guesses."""
    out = {"key_installed": configured(), "key_file": KEY_FILE, "api": API,
           "catalogue": None, "account_balance": None, "error": None}
    if not configured():
        out["error"] = "no key: demo catalogue is being served"
        return out
    try:
        out["catalogue"] = len(products(country="US", limit=5))
    except BitrefillError as exc:
        out["error"] = str(exc)
        return out
    try:
        out["account_balance"] = balance()
    except BitrefillError as exc:
        out["account_balance"] = {"unavailable": str(exc)[:160]}
    return out
