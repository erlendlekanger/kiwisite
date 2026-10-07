"""FOMOCARD: currency rates, so a card priced in kroner can still be quoted.

Keyless sources, ECB reference rates first. A rate we cannot fetch is None, and
a quote built on a converted figure is always marked as an estimate: the number
that settles is the one on the supplier's invoice, not this one.
"""
from __future__ import annotations

import threading
import time

from op import engine

SOURCES = (
    ("frankfurter", "https://api.frankfurter.dev/v1/latest?base={base}&symbols=USD"),
    ("er-api", "https://open.er-api.com/v6/latest/{base}"),
)
TTL_S = 3600

_lock = threading.RLock()
_cache: dict[str, tuple[float, float | None, str]] = {}


def _fetch(base: str) -> tuple[float | None, str]:
    for name, url in SOURCES:
        try:
            d = engine.http_json(url.format(base=base), timeout=12)
        except RuntimeError:
            continue
        rate = (d.get("rates") or {}).get("USD")
        try:
            r = float(rate)
        except (TypeError, ValueError):
            continue
        if r > 0:
            return r, name
    return None, "none"


def to_usd(amount: float, currency: str) -> tuple[float | None, str | None]:
    """(usd, source). USD passes straight through; anything unreadable is None."""
    cur = (currency or "USD").upper()
    if cur in ("USD", "USDC"):
        return round(float(amount), 2), None
    with _lock:
        hit = _cache.get(cur)
        if hit and time.time() - hit[0] < TTL_S:
            rate, src = hit[1], hit[2]
        else:
            rate, src = _fetch(cur)
            _cache[cur] = (time.time(), rate, src)
    if rate is None:
        return None, None
    return round(float(amount) * rate, 2), src


def rate(currency: str) -> float | None:
    usd, _ = to_usd(1.0, currency)
    return usd
