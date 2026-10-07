"""FOMOCARD: follow a redemption link and read the card off it.

Some shops do not hand back a card number. Nike comes back as a link to a reward
page plus a PIN, and the number that a checkout actually wants is printed on that
page. Left as it arrives, the buyer is given six digits that fit nowhere and a URL
they have to work out for themselves.

So the page is fetched once, on their behalf, and the card read off it. That is a
plain read of a page their own code addresses, and it is why the site can show a
number instead of a puzzle.

Two things this will not do. It does not submit anything: if a page asks for
input, that is the buyer's to give, not ours to guess. And it does not touch a
captcha, ever; a page gated by one is handed back as a link with an honest word
about why.
"""
from __future__ import annotations

import re
import threading
import urllib.error
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml"}
TIMEOUT = 25
MAX_BYTES = 400_000

# Hosts we have looked at and know print the card. Anywhere else is left alone
# rather than scraped on spec.
KNOWN = ("redeem.yourdigitalreward.com",)

_lock = threading.RLock()
_cache: dict[str, dict] = {}

_TAGS = re.compile(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>")
_LABELLED = re.compile(r"(?i)\byour\s+(code|pin|card\s*number|gift\s*card\s*number)\b[\s:]*([0-9][0-9 \-]{3,30})")
_CAPTCHA_FORM = re.compile(r"(?i)data-sitekey=|g-recaptcha-response|h-captcha-response|cf-turnstile-response")


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", _TAGS.sub(" ", html))).strip()


def looks_gated(html: str) -> bool:
    """A captcha that is merely loaded by a template is not a gate; one wired to a
    form is. We only refuse the second kind, and we never try to answer either."""
    return bool(_CAPTCHA_FORM.search(html)) and "<form" in html.lower()


def read(link: str) -> dict:
    """{code, pin, source, note}. Empty when nothing could be read, which leaves
    the link on the page exactly as it was."""
    if not link or not link.startswith("https://"):
        return {}
    host = link.split("/")[2].lower()
    if not any(host == k or host.endswith("." + k) for k in KNOWN):
        return {"note": "not a page we read from"}
    with _lock:
        hit = _cache.get(link)
    if hit is not None:
        return hit

    try:
        req = urllib.request.Request(link, headers=UA)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            html = r.read(MAX_BYTES).decode("utf-8", "ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as exc:
        return {"note": f"could not open the reward page ({str(exc)[:60]})"}

    if looks_gated(html):
        out = {"note": "the reward page asks you to prove you are human, so it has to be opened by hand"}
        with _lock:
            _cache[link] = out
        return out

    found: dict[str, str] = {}
    for label, digits in _LABELLED.findall(_text(html)):
        key = "pin" if label.lower() == "pin" else "code"
        value = re.sub(r"[\s\-]", "", digits)
        # the page prints the number twice; the first read of each is enough
        found.setdefault(key, value)
    if not found.get("code"):
        return {"note": "nothing on the reward page looked like a card number"}

    out = {"code": found["code"], **({"pin": found["pin"]} if found.get("pin") else {}), "source": link}
    with _lock:
        _cache[link] = out
    return out


def enrich(info: dict | None) -> dict | None:
    """Fold whatever the reward page says into the supplier's own answer. The
    link is kept either way, so nothing is ever hidden from the buyer."""
    if not isinstance(info, dict):
        return info
    link = info.get("link") or info.get("url") or info.get("redemption_url")
    if not link or info.get("code"):
        return info
    got = read(link)
    if not got.get("code"):
        return {**info, **({"note": got["note"]} if got.get("note") else {})}
    merged = {**info, "code": got["code"]}
    if got.get("pin"):
        merged["pin"] = got["pin"]
    return merged
