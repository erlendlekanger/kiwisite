"""FOMOCARD: turn a supplier product image into a mark we can lay out like our own.

The supplier's artwork carries the shop's background baked in and a wide, uneven
margin. Dropped straight onto a tile it reads as a photograph of a gift card,
while an icon from our own set reads as a logo, and a grid of both looks broken.

So each one is fetched once at a size where it is still crisp, its flat
background lifted to transparency and the margin trimmed to the ink. The result
is cached on disk and served from there afterwards. Doing it here rather than in
a build step means it covers the whole live catalogue, however large it grows,
without anyone having to remember to re-run anything.

Nothing is redrawn. The shapes and the colours are the shop's own.
"""
from __future__ import annotations

import json
import os
import threading
import urllib.error
import urllib.request
from collections import Counter
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "assets" / "shots"
SRC = "https://cdn.bitrefill.com/primg/w1000h400i1/{pid}.webp"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FOMOCARD/1.0"}

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_failed: set[str] = set()


def _lock_for(pid: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(pid, threading.Lock())


def cached_path(pid: str) -> Path:
    return CACHE / f"{pid}.png"


def _clean(raw: bytes):
    """Background to transparency, then trim to the ink. Imported lazily so the
    server still runs for everything else if Pillow or numpy is not installed."""
    import numpy as np
    from PIL import Image

    img = Image.open(BytesIO(raw))
    img.load()
    a = np.asarray(img.convert("RGB"))
    h, w, _ = a.shape
    m = max(2, h // 12)
    border = np.concatenate([a[:m].reshape(-1, 3), a[-m:].reshape(-1, 3),
                             a[:, :m].reshape(-1, 3), a[:, -m:].reshape(-1, 3)])
    common = Counter(map(tuple, (border // 12 * 12))).most_common(1)[0][0]
    near = border[np.abs(border.astype(int) - np.array(common)).sum(axis=1) < 40]
    bg = (near.mean(axis=0) if len(near) else np.array(common, dtype=float))

    dist = np.abs(a.astype(np.float32) - bg).sum(axis=2)
    alpha = np.clip(dist / 90.0, 0, 1)
    out = np.zeros((*alpha.shape, 4), np.uint8)
    out[..., :3] = a
    out[..., 3] = (alpha * 255).round().astype(np.uint8)
    mark = Image.fromarray(out, "RGBA")

    ys, xs = np.where(out[..., 3] > 10)
    if not len(ys):
        return None
    pad = 6
    mark = mark.crop((max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad),
                      min(mark.width, int(xs.max()) + 1 + pad), min(mark.height, int(ys.max()) + 1 + pad)))
    if mark.width < 8 or mark.height < 8:
        return None
    return mark


def mark(pid: str) -> Path | None:
    """The cleaned mark for one product, fetching and caching it the first time.
    None when the supplier has no artwork for it, which the page handles by
    falling back to the shop's name."""
    if not pid or "/" in pid or "\\" in pid or pid in _failed:
        return None
    path = cached_path(pid)
    if path.is_file():
        return path
    with _lock_for(pid):
        if path.is_file():
            return path
        try:
            req = urllib.request.Request(SRC.format(pid=pid), headers=UA)
            with urllib.request.urlopen(req, timeout=20) as r:
                raw = r.read()
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
            _failed.add(pid)
            return None
        try:
            cleaned = _clean(raw)
        except Exception:  # noqa: BLE001
            _failed.add(pid)
            return None
        if cleaned is None:
            _failed.add(pid)
            return None
        if not WRITABLE:
            return None          # read-only host: the page falls back to the CDN
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        cleaned.save(tmp, format="PNG", optimize=True)   # the .part name hides the format
        tmp.replace(path)          # so a half-written file is never served
        return path


# Which marks ship with the build. On a serverless host the function cannot see
# the static files, and it cannot write either, so the manifest is the answer to
# "do we have this one" and the CDN is the answer when we do not.
try:
    SHIPPED: set[str] = set(json.loads((Path(__file__).resolve().parent / "shots.json").read_text(encoding="utf-8")))
except (OSError, ValueError):
    SHIPPED = set()

WRITABLE = os.environ.get("VERCEL") is None


def have(pid: str) -> bool:
    if not pid:
        return False
    return pid in SHIPPED or (WRITABLE and cached_path(pid).is_file())
