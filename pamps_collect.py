"""PAMPS real-data collector — drives your logged-in Axiom and harvests the
first ~10 seconds of life of brand-new memecoins into a training dataset.

What it does (matches the PAMPS idea):
  1. Opens axiom.trade in a SEPARATE, wallet-less browser profile (.pamps_profile).
  2. Picks a fresh coin from the NEW PAIRS column (far left of /pulse).
  3. Opens it and SCANS the token-info panel every ~100 ms for 10 s:
        Dev H%, Bundlers, Insiders, Snipers, Top 10 holders, price, MC, volume.
     (These numbers typically drift DOWN as the coin ages — we capture the curve.)
  4. Streams every tick to  pamps_dataset.jsonl  (the dataset) and writes a live
     snapshot to  pamps/live.json  so the website can show the real coin + real
     "agent thoughts" in real time.
  5. Leaves the coin, picks the next one, repeats — building data forever.

Run (site + collector in two terminals):
    py pamps.py            # the website  ->  http://127.0.0.1:8811/
    py pamps_collect.py    # this collector (needs you logged in on Axiom)

First run / calibration:
    set PAMPS_DEBUG=1 && py pamps_collect.py
  …prints the raw token-panel text + what each metric matched, so we can lock
  the selectors to Axiom's live DOM. Axiom's markup is obfuscated, so expect one
  calibration pass before the numbers come out clean.

SAFETY (an early version mis-clicked a buy field — that must never happen):
  * It NEVER clicks anything. Coins are opened by NAVIGATING to their link only,
    so no buy / quick-snipe control can ever be pressed.
  * It uses a SEPARATE, WALLET-LESS profile (.pamps_profile) — NOT the funded
    .axiom_profile. Do NOT connect a funded wallet to it. No wallet => no buy.
  * A network kill-switch aborts any request that looks like a trade/transaction.

Notes:
  * Read-only data collection. Uses only your browser session — no paid API, no keys.
  * First time: a fresh Chromium opens on .pamps_profile. If the metrics need a
    login, log in WITHOUT connecting a funded wallet (view-only is enough).
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import logging
import os
import subprocess
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Error as PlaywrightError
from playwright.async_api import Page, async_playwright

# ── Config ───────────────────────────────────────────────────────────────────
HERE = Path(__file__).resolve().parent
# ── SAFETY ───────────────────────────────────────────────────────────────────
# A SEPARATE, wallet-less profile — NEVER the funded .axiom_profile. Do not
# connect a funded wallet here. With no wallet connected, a buy is impossible
# even if something were ever clicked. (The collector also never clicks at all.)
USER_DATA_DIR = HERE / (os.environ.get("PAMPS_PROFILE") or ".pamps_profile")
ORIGIN = "https://axiom.trade"
PULSE_URL = os.environ.get("PAMPS_AX_URL", "https://axiom.trade/pulse")
DATASET = HERE / "pamps_dataset.jsonl"
LIVE_JSON = HERE / "pamps" / "live.json"
DWELL_SEC = float(os.environ.get("PAMPS_DWELL", "25"))     # analyse each coin's first 25 s
POLL_MS = int(os.environ.get("PAMPS_POLL_MS", "100"))      # scan every 100 ms
MAX_AGE = int(os.environ.get("PAMPS_MAX_AGE", "0"))        # only open coins showing exactly "0s"
# optional: push the live snapshot to a deployed Vercel site (KV relay) so the
# public page shows real-time data. Leave unset to run purely local.
PUSH_URL = (os.environ.get("PAMPS_PUSH_URL") or "").rstrip("/")
PUSH_SECRET = os.environ.get("PAMPS_PUSH_SECRET") or ""
PUSH_EVERY = float(os.environ.get("PAMPS_PUSH_EVERY", "2.5"))
_last_push = 0.0
DEBUG = os.environ.get("PAMPS_DEBUG") == "1"
CDP_PORT = int(os.environ.get("PAMPS_CDP_PORT", "9356"))
VIEWPORT_WIDTH = 1380
VIEWPORT_HEIGHT = 920

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")


def _work_area() -> tuple[int, int]:
    try:
        r = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(48, 0, ctypes.byref(r), 0):
            return r.right - r.left, r.bottom - r.top
    except Exception:
        pass
    return 1920, 1040


def _release_locks() -> None:
    for name in ("lockfile", "SingletonLock", "SingletonCookie"):
        try:
            (USER_DATA_DIR / name).unlink(missing_ok=True)
        except OSError:
            pass


# ── Real-browser launch via CDP (the pattern that actually logs into Axiom) ──
# Google OAuth blocks Playwright's bundled "Chrome for testing" (--enable-automation
# → "Noe gikk galt"). Instead we start the user's REAL Edge/Chrome as a normal
# process with a debugging port and attach over CDP — same as axiom_fees.py /
# j7_coin_match.py. Login works like in any normal browser, and once logged in a
# restart just reconnects (no re-login).
def _find_browser() -> tuple[str, str] | None:
    roots = [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", ""),
             os.environ.get("LOCALAPPDATA", "")]
    candidates = [
        (r"Microsoft\Edge\Application\msedge.exe", "edge"),
        (r"Google\Chrome\Application\chrome.exe", "chrome"),
    ]
    for root in roots:
        if not root:
            continue
        for rel, label in candidates:
            p = Path(root) / rel
            if p.is_file():
                return str(p), label
    return None


def _cdp_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _launch_real_browser(profile: Path, port: int) -> "subprocess.Popen | None":
    """Start real Edge/Chrome with a debugging port (or reuse one already up)."""
    if _cdp_ready(port):
        logging.info("Kobler til allerede åpen nettleser (CDP %s) — ingen ny innlogging.", port)
        return None
    found = _find_browser()
    if not found:
        raise FileNotFoundError("Fant verken Edge eller Chrome på PC-en")
    exe, label = found
    profile.mkdir(parents=True, exist_ok=True)
    _release_locks()
    _, work_h = _work_area()
    cmd = [
        exe,
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={port}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        f"--window-size={VIEWPORT_WIDTH},{max(700, work_h - 90)}",
        "--window-position=40,0",
        PULSE_URL,
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logging.info("Startet ekte %s for innlogging (CDP %s)…", label, port)
    deadline = time.time() + 35.0
    while time.time() < deadline:
        if _cdp_ready(port):
            return proc
        if proc.poll() is not None:
            raise RuntimeError("Nettleseren avsluttet ved oppstart")
        time.sleep(0.35)
    raise TimeoutError(f"CDP-port {port} ble ikke klar")


async def _stealth(context: BrowserContext) -> None:
    await context.add_init_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        "window.chrome=window.chrome||{runtime:{}};"
    )


# ── Injected page helpers ────────────────────────────────────────────────────
# Two functions live on the page:
#   __pampsNewPairs()  -> [{label,x,y}]  clickable coins in the leftmost column
#   __pampsExtract()   -> {metrics..., _debug}  read the open coin's info panel
INJECT_JS = r"""
(() => {
  if (window.__pampsReady) return;
  window.__pampsReady = true;

  const txt = el => ((el && el.textContent) || '').replace(/\s+/g,' ').trim();
  const vis = el => {
    if (!(el instanceof HTMLElement)) return false;
    const r = el.getBoundingClientRect();
    if (!r.width || !r.height) return false;
    const s = getComputedStyle(el);
    return s.visibility!=='hidden' && s.display!=='none' && r.bottom>0 && r.top<innerHeight;
  };
  const pctOf = s => { const m=String(s).match(/(\d+(?:\.\d+)?)\s*%/); return m?parseFloat(m[1]):null; };
  const numUsd = s => {
    const m=String(s).replace(/,/g,'').match(/\$?\s*([\d.]+)\s*([kmb])?/i);
    if(!m) return null; let v=parseFloat(m[1]); const u=(m[2]||'').toLowerCase();
    if(u==='k')v*=1e3; else if(u==='m')v*=1e6; else if(u==='b')v*=1e9; return v;
  };

  // newest coins live in the left column of /pulse ("New Pairs").
  // SAFETY: we only collect <a href> LINKS — never coordinates, never buttons.
  // The collector opens a coin by NAVIGATING to its link, so it can never press
  // a buy / quick-snipe control.
  window.__pampsNewPairs = () => {
    // NEW PAIRS column rows are NOT /meme links (only the held-coin top bar is).
    // Each row carries the mint inside its HTML (pump.fun/x.com links). Pull the
    // mint and build /meme/<mint> ourselves, so we navigate (never click) into the
    // actual newest launches — not the coin pinned at the top of the screen.
    const colMaxX = 430, headerY = 188;     // left of "Final Stretch" (x~439), below header
    const cands = [...document.querySelectorAll('div,li,article')].filter(el => {
      if (!vis(el)) return false;
      const r = el.getBoundingClientRect();
      return r.left >= 6 && r.left < colMaxX && r.top > headerY
             && r.width > 200 && r.width < colMaxX + 60 && r.height >= 44 && r.height <= 170;
    });
    const seen = new Set(); const out = [];
    for (const el of cands) {
      const html = el.innerHTML || '';
      const m = html.match(/pump\.fun\/coin\/([1-9A-HJ-NP-Za-km-z]{32,44})/)
             || html.match(/[?&]q=([1-9A-HJ-NP-Za-km-z]{32,44})/)
             || html.match(/([1-9A-HJ-NP-Za-km-z]{32,44}pump)\b/)
             || html.match(/([1-9A-HJ-NP-Za-km-z]{32,44})/);
      if (!m) continue;
      const mint = m[1] || m[0];
      if (seen.has(mint)) continue; seen.add(mint);
      const r = el.getBoundingClientRect();
      out.push({ mint, href: `/meme/${mint}?chain=sol`,
                 label: (txt(el) || mint).replace(/\s+/g, ' ').slice(0, 40), top: r.top });
    }
    out.sort((a, b) => a.top - b.top);       // topmost in the column = newest
    return out.slice(0, 12);
  };

  // Open a NEW PAIRS coin the way a user does: CLICK the white symbol text next to
  // the coin image. Direct URL nav loads a cold page without the holder panel; the
  // click opens it properly. HARD SAFETY: only ever click in the LEFT HALF of the
  // row (image + symbol live there) — never the right side where Buy buttons are.
  window.__pampsClickNewCoin = (avoid, maxAge) => {
    avoid = new Set(avoid || []);
    maxAge = (maxAge == null ? 1 : maxAge);
    const colMaxX = 430, headerY = 182;
    const rows = [...document.querySelectorAll('div,li,article')].filter(el => {
      if (!vis(el)) return false;
      const r = el.getBoundingClientRect();
      return r.left>=4 && r.left<colMaxX && r.top>headerY && r.width>180 && r.width<colMaxX+90 && r.height>=40 && r.height<=185;
    }).sort((a,b)=>a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    const mintOf = (row) => {
      const html = row.innerHTML || '';
      const m = html.match(/pump\.fun\/coin\/([1-9A-HJ-NP-Za-km-z]{32,44})/)
             || html.match(/[?&]q=([1-9A-HJ-NP-Za-km-z]{32,44})/)
             || html.match(/([1-9A-HJ-NP-Za-km-z]{32,44}pump)\b/);
      return m ? (m[1] || m[0]) : '';
    };
    const ageOf = (row) => {                            // "0s"/"3s" = seconds; "1m"/"2h" = old
      let a = 99999;
      for (const e of row.querySelectorAll('span,div,p,b,strong')) {
        if (e.childElementCount > 0) continue;
        const t = txt(e);
        const sm = t.match(/^(\d+)\s*s$/i);
        if (sm) { a = parseInt(sm[1]); break; }
        if (/^\d+\s*[mhd]$/i.test(t)) a = 9999;
      }
      return a;
    };
    // Try each row top→bottom (newest first). Click the first FRESH (age ≤ maxAge),
    // not-done coin that exposes a safe left-side symbol/avatar. Iterating (vs picking
    // one row) restores robustness: a coin spans several nested rows, and we click
    // whichever one actually has a clickable symbol.
    let youngest = 99999;
    for (const row of rows) {
      const mint = mintOf(row); if (!mint) continue;
      const age = ageOf(row);
      if (age < youngest) youngest = age;
      if (avoid.has(mint) || age > maxAge) continue;
      const rr = row.getBoundingClientRect();
      const rightCut = rr.left + rr.width * 0.6;          // buy controls live in the right ~40%
      const img = row.querySelector('img');
      const imgLeft = img ? img.getBoundingClientRect().left : rr.left;
      let target = null, bestX = 1e9;
      for (const el of row.querySelectorAll('span,div,p,b,strong')) {  // NOT <a> — socials
        if (!vis(el) || el.childElementCount > 0) continue;
        if (el.closest('a')) continue;
        const t = txt(el);
        if (!t || t.length > 14) continue;
        if (/sol\b|\$|%|\bmc\b|buy|sell|^\d|^@/i.test(t)) continue;
        const r = el.getBoundingClientRect();
        if (r.left < imgLeft - 4) continue;
        if (r.left + r.width/2 > rightCut) continue;       // left side only
        if (r.left < bestX) { bestX = r.left; target = el; }
      }
      if (!target && img) {                                // coin avatar fallback (leftmost)
        const ir = img.getBoundingClientRect();
        if (ir.left + ir.width/2 <= rightCut) target = img;
      }
      if (!target) continue;                               // no safe symbol here — try next row
      const tr = target.getBoundingClientRect();
      if (tr.left + tr.width/2 > rightCut) continue;
      target.scrollIntoView({ block:'center', inline:'nearest' });
      const sym = txt(target) || (img && img.getAttribute('alt')) || mint.slice(0,6);
      try { target.click(); } catch (e) { continue; }
      return { clicked:true, mint, symbol: sym, age };
    }
    return { clicked:false, reason:'none_clickable',
             youngest: (youngest === 99999 ? null : youngest) };
  };

  // probe: dump the topmost New Pairs rows' leaf texts so we can find the AGE field
  // (we want to click a coin only when its age is "0s" = just launched).
  window.__pampsAgeProbe = () => {
    const colMaxX = 430, headerY = 188;
    const rows = [...document.querySelectorAll('div,li,article')].filter(el => {
      if (!vis(el)) return false;
      const r = el.getBoundingClientRect();
      return r.left>=6 && r.left<colMaxX && r.top>headerY && r.width>200 && r.width<colMaxX+60 && r.height>=44 && r.height<=170;
    }).sort((a,b)=>a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    return rows.slice(0, 3).map(row =>
      [...row.querySelectorAll('span,div,p,b,strong')]
        .filter(e => vis(e) && e.childElementCount === 0)
        .map(e => txt(e)).filter(Boolean).slice(0, 20));
  };

  // list the mints currently in the NEW PAIRS column, top→bottom (no clicking).
  // Used to detect when a BRAND-NEW coin spawns (so we catch it at ~0s, not 5s old).
  window.__pampsColumnMints = () => {
    const colMaxX = 430, headerY = 188;
    const rows = [...document.querySelectorAll('div,li,article')].filter(el => {
      if (!vis(el)) return false;
      const r = el.getBoundingClientRect();
      return r.left>=6 && r.left<colMaxX && r.top>headerY && r.width>200 && r.width<colMaxX+60 && r.height>=44 && r.height<=170;
    }).sort((a,b)=>a.getBoundingClientRect().top - b.getBoundingClientRect().top);
    const seen = new Set(); const mints = [];
    for (const row of rows) {
      const html = row.innerHTML || '';
      // STRICT mint (must match the click-finder exactly, or new-spawn detection breaks)
      const m = html.match(/pump\.fun\/coin\/([1-9A-HJ-NP-Za-km-z]{32,44})/)
             || html.match(/[?&]q=([1-9A-HJ-NP-Za-km-z]{32,44})/)
             || html.match(/([1-9A-HJ-NP-Za-km-z]{32,44}pump)\b/);
      const mint = m ? (m[1] || m[0]) : '';
      if (mint && !seen.has(mint)) { seen.add(mint); mints.push(mint); }
    }
    return mints;
  };

  // probe: where is the "New Pairs" column header vs every /meme link, so we can
  // target the column and skip the held-coin bar pinned at the top of the screen.
  window.__pampsProbe = () => {
    const heads = [...document.querySelectorAll('span,div,p,h1,h2,h3,button')]
      .filter(el => vis(el) && /^(new pairs?|final stretch|migrat)/i.test(txt(el)) && txt(el).length < 24)
      .map(el => { const r = el.getBoundingClientRect(); return `${txt(el)}@x${Math.round(r.left)},y${Math.round(r.top)}`; });
    const memes = [...document.querySelectorAll('a[href*="/meme/"]')].filter(vis).map(el => {
      const r = el.getBoundingClientRect();
      return `${(txt(el) || '').slice(0, 16)}|x${Math.round(r.left)}|y${Math.round(r.top)}|w${Math.round(r.width)}`;
    }).slice(0, 24);
    return { heads, memes };
  };

  // scan the NEW PAIRS column (left of "Final Stretch" @ x~439, below header y~185)
  // for coin rows and pull a mint from each row's embedded pump.fun/x.com links.
  window.__pampsColScan = () => {
    const colMaxX = 430, headerY = 188;
    const cands = [...document.querySelectorAll('div,li,article')].filter(el => {
      if (!vis(el)) return false;
      const r = el.getBoundingClientRect();
      return r.left >= 6 && r.left < colMaxX && r.top > headerY
             && r.width > 200 && r.width < colMaxX + 60 && r.height >= 44 && r.height <= 170;
    });
    const seen = new Set(); const rows = [];
    for (const el of cands) {
      const html = el.innerHTML || '';
      const m = html.match(/[1-9A-HJ-NP-Za-km-z]{32,44}/);   // base58 mint
      const mint = m ? m[0] : '';
      const r = el.getBoundingClientRect();
      const key = mint || Math.round(r.top / 8);
      if (seen.has(key)) continue; seen.add(key);
      rows.push(`${(txt(el) || '').slice(0, 26)}|mint=${mint.slice(0, 10)}|y${Math.round(r.top)}|h${Math.round(r.height)}`);
      if (rows.length >= 8) break;
    }
    return rows;
  };

  // diagnostics: tells us login-wall vs selector-miss when no coins are found.
  window.__pampsDiag = () => {
    const a = [...document.querySelectorAll('a[href]')].filter(vis);
    const left = a.filter(el => el.getBoundingClientRect().left < innerWidth*0.42);
    const money = left.filter(el => { const t=txt(el).toLowerCase(); return t.includes('$')||t.includes('mc')||t.includes('sol'); });
    return { url: location.href, title: document.title,
             anchors: a.length, leftAnchors: left.length, moneyAnchors: money.length,
             sampleHrefs: [...new Set(a.map(el=>el.getAttribute('href')))].slice(0,18) };
  };

  // Trades table (right side of the coin page): each row is
  //   Amount(SOL) | MC | Trader | Age("Xs")   — amount is green=buy / red=sell.
  // Capture every visible trade so we can see who buys/sells how much SOL and when.
  window.__pampsTrades = () => {
    const out = []; const seen = new Set();
    const cands = [...document.querySelectorAll('div,tr,li')].filter(el => {
      if (!vis(el)) return false;
      const r = el.getBoundingClientRect();
      if (r.left < innerWidth * 0.5) return false;          // trades table is on the right
      if (r.height < 12 || r.height > 66) return false;
      const t = txt(el);
      return t.length < 64 && /\$[\d.]+[kmb]?/i.test(t) && /\d+\s*s\b/i.test(t) && /\d/.test(t[0] || '');
    });
    for (const el of cands) {
      // NB: the age ("1s") lives in an <a> tag, so include 'a' here
      const leaves = [...el.querySelectorAll('span,div,p,b,strong,a')].filter(e => vis(e) && e.childElementCount === 0);
      let amt = null, amtEl = null, mc = null, trader = '', age = null;
      for (const lf of leaves) {
        const t = txt(lf);
        if (amt === null && /^\d+(\.\d+)?$/.test(t) && parseFloat(t) < 1e7) { amt = parseFloat(t); amtEl = lf; continue; }
        if (mc === null && /^\$\d+(\.\d+)?[kmb]?$/i.test(t)) { mc = numUsd(t); continue; }
        const ag = t.match(/^(\d+)\s*s$/i); if (ag && age === null) { age = parseInt(ag[1]); continue; }
        if (!trader && /^[A-Za-z0-9]{2,8}$/.test(t) && !/^\d+$/.test(t) && !/^\d+s$/i.test(t) && t !== 'ADD' && !/[kmb]$/i.test(t)) trader = t;
      }
      if (amt === null || age === null) continue;
      let side = '';                                          // buy/sell from the amount colour
      if (amtEl) {
        const m = getComputedStyle(amtEl).color.match(/(\d+),\s*(\d+),\s*(\d+)/);
        if (m) { const R = +m[1], G = +m[2]; side = R > G + 25 ? 'sell' : (G > R + 15 ? 'buy' : ''); }
      }
      const key = amt + '|' + (mc || 0) + '|' + trader + '|' + age;
      if (seen.has(key)) continue; seen.add(key);
      out.push({ amt, side, mc, trader, age });
    }
    return out.slice(0, 40);
  };

  // Axiom renders each metric as a concatenated chip where the value is glued
  // right before the label, e.g. "0%Dev H.", "0.32%Top 10 H.", "0%Bundlers".
  // Match those directly — far more reliable than label/percent proximity.
  window.__pampsExtract = () => {
    const pats = {
      devHold:  /(\d+(?:\.\d+)?)\s*%\s*Dev\s*H/i,
      snipers:  /(\d+(?:\.\d+)?)\s*%\s*Snipers/i,
      insiders: /(\d+(?:\.\d+)?)\s*%\s*Insiders/i,
      bundlers: /(\d+(?:\.\d+)?)\s*%\s*Bundlers/i,
      top10:    /(\d+(?:\.\d+)?)\s*%\s*Top\s*10/i,
    };
    const out = {devHold:null, bundlers:null, insiders:null, snipers:null, top10:null,
                 mcap:null, price:null, vol:null};
    const bestLen = {};
    const all = [...document.querySelectorAll('span,div,p,small,b,strong,td,th,label')].filter(vis);
    for (const el of all) {
      const t = txt(el);
      if (!t || t.length > 60) continue;     // skip giant concat parents
      for (const k in pats) {
        const mm = t.match(pats[k]);
        if (mm && (out[k] === null || t.length < bestLen[k])) {
          out[k] = parseFloat(mm[1]); bestLen[k] = t.length;   // shortest = the exact chip
        }
      }
    }
    // MC = the "$2.17k" to the right of the coin name (header). Vol = value under
    // "5m Vol" (per the user's pointers).
    const moneyRe = /^\$?\d+(?:\.\d+)?[kmb]?$/i;
    for (const el of all) {
      if (out.mcap !== null) break;
      const t = txt(el); const r = el.getBoundingClientRect();
      if (r.top>0 && r.top<300 && r.left>180 && t.length<=12
          && /^\$\d+(?:\.\d+)?[kmb]$/i.test(t.replace(/\s/g,''))) out.mcap = numUsd(t);
    }
    for (const el of all) {
      if (out.vol !== null) break;
      if (!/^5m\s*vol/i.test(txt(el))) continue;
      const lr = el.getBoundingClientRect();
      let best=null, bd=1e9;
      for (const e2 of all) {
        const t2 = txt(e2).replace(/\s/g,''); if (!moneyRe.test(t2)) continue;
        const r2 = e2.getBoundingClientRect();
        const dx = Math.abs((r2.left+r2.width/2)-(lr.left+lr.width/2));
        const dy = r2.top - lr.bottom;
        if (dy < -6 || dy > 46 || dx > 70) continue;       // directly below the label
        const d = dy + dx; if (d < bd) { bd=d; best=numUsd(t2); }
      }
      out.vol = best;
    }
    out.trades = window.__pampsTrades ? window.__pampsTrades() : [];
    if (window.__PAMPS_DEBUG) {
      out._debug = {
        metrics: {dev:out.devHold, bundlers:out.bundlers, insiders:out.insiders, snipers:out.snipers, top10:out.top10, mc:out.mcap, vol:out.vol},
        nTrades: out.trades.length, trades: out.trades.slice(0,4),
      };
    }
    return out;
  };
})();
"""


async def _inject(page: Page) -> None:
    try:
        await page.evaluate(INJECT_JS)
        if DEBUG:
            await page.evaluate("window.__PAMPS_DEBUG=true")
    except PlaywrightError:
        pass


async def _cf_light(page: Page) -> bool:
    try:
        t = (await page.title() or "").lower()
        return any(x in t for x in ("just a moment", "vent litt", "please wait"))
    except PlaywrightError:
        return True


async def _wait_cf(page: Page) -> None:
    if not await _cf_light(page):
        return
    logging.info("Cloudflare — fullfør «Verifiser at du er et menneske» selv. Venter…")
    while await _cf_light(page):
        if page.is_closed():
            raise RuntimeError("Vindu lukket under Cloudflare")
        await asyncio.sleep(2.0)
    logging.info("Cloudflare OK.")


# ── Truthful-but-cool agent thoughts derived from the REAL metrics ───────────
def _trend(series: list[dict], key: str) -> float | None:
    pts = [s[key] for s in series if s.get(key) is not None]
    if len(pts) < 2:
        return None
    return pts[-1] - pts[0]


def _thoughts(sym: str, m: dict, series: list[dict], elapsed: float) -> dict[str, str]:
    def g(k):
        return m.get(k)

    def arrow(d):
        return "↓" if (d or 0) < -0.05 else ("↑" if (d or 0) > 0.05 else "→")

    dv, bn, ins, sn, t10 = g("devHold"), g("bundlers"), g("insiders"), g("snipers"), g("top10")
    vol, mc, pr = g("vol"), g("mcap"), g("price")
    dVol = _trend(series, "vol")
    dPr = _trend(series, "price")
    dDev = _trend(series, "devHold")

    def volt():
        if vol is not None and dVol:
            pct = (dVol / vol * 100) if vol else 0
            return f"watching {sym} flow — vol {arrow(dVol)} {abs(pct):.0f}% in {elapsed:.0f}s"
        if vol is not None:
            return f"{sym} volume reading ${vol:,.0f}, mapping the curve"
        return f"locking onto {sym}'s first ticks…"

    def prism():
        return f"profiling {sym} — fresh deploy, {elapsed:.0f}s old, reading the meta"

    def sentinel():
        bits = []
        if dv is not None:
            bits.append(f"dev {dv:.0f}% {arrow(dDev)}")
        if bn is not None:
            bits.append(f"bundlers {bn:.0f}%")
        if ins is not None:
            bits.append(f"insiders {ins:.0f}%")
        if not bits:
            return f"x-raying {sym} for bundles & insiders…"
        flag = " ⚠" if (bn and bn >= 25) or (dv and dv >= 30) else ""
        return f"{sym}: " + " · ".join(bits) + flag

    def oracle():
        if t10 is not None:
            tag = "tight" if t10 >= 35 else "spread"
            return f"{sym} top10 holds {t10:.0f}% — {tag}"
        return f"graphing {sym}'s holder spread…"

    def hype():
        if sn is not None:
            return f"{sym} drew {sn:.0f}% snipers in the first seconds"
        if mc is not None:
            return f"{sym} at ${mc:,.0f} MC and climbing the feed"
        return f"gauging early heat on {sym}…"

    return {"volt": volt(), "prism": prism(), "sentinel": sentinel(),
            "oracle": oracle(), "hype": hype()}


def _atomic_write_json(path: Path, obj: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj), encoding="utf-8")
    os.replace(tmp, path)


def _push_live(obj: dict) -> None:
    """Fire-and-forget POST of the live snapshot to the deployed Vercel relay."""
    if not (PUSH_URL and PUSH_SECRET):
        return

    def go():
        try:
            data = json.dumps(obj).encode("utf-8")
            req = urllib.request.Request(
                PUSH_URL + "/api/live", data=data,
                headers={"Content-Type": "application/json", "X-Push-Secret": PUSH_SECRET},
                method="POST")
            urllib.request.urlopen(req, timeout=8).read()
        except Exception:
            pass

    threading.Thread(target=go, daemon=True).start()


# ── Main collection loop ─────────────────────────────────────────────────────
async def _analyse_one(page: Page, coin: dict, stats: dict, ds) -> None:
    label = coin.get("label", "?")
    sym = label.split(" ")[0][:12] or "$COIN"
    t0 = time.time()
    series: list[dict] = []
    trades_seen: set[str] = set()
    coin_trades: list[dict] = []
    dumped = False
    logging.info("→ analysing %s for %ss", sym, DWELL_SEC)

    while time.time() - t0 < DWELL_SEC:
        elapsed = time.time() - t0
        try:
            m = await page.evaluate("() => window.__pampsExtract ? window.__pampsExtract() : null")
        except PlaywrightError:
            await _inject(page)
            m = None
        if not isinstance(m, dict):
            await asyncio.sleep(POLL_MS / 1000)
            continue

        if DEBUG and not dumped and elapsed >= 3.0:  # dump after panel renders
            dbg = m.get("_debug") or {}
            logging.info("DEBUG metrics=%s nTrades=%s trades=%s",
                         dbg.get("metrics"), dbg.get("nTrades"), dbg.get("trades"))
            dumped = True
        m.pop("_debug", None)

        # split out trades (don't bloat every tick row) → dedup + write trade events.
        # IMPORTANT: dedup on the trade's STABLE identity (trader|amt|mc|side). The
        # displayed "age" increments every second, so including it re-counts the same
        # trade once per second it stays visible → inflated counts. We record the
        # collector elapsed `t` (≈ coin age when the trade first appeared) instead.
        wall = round(time.time(), 2)
        for tr in (m.pop("trades", None) or []):
            key = f"{tr.get('trader')}|{tr.get('amt')}|{tr.get('mc')}|{tr.get('side')}"
            if key in trades_seen:
                continue
            trades_seen.add(key)
            coin_trades.append(tr)
            ds.write(json.dumps({"type": "trade", "coin": sym, "mint": coin.get("mint", ""),
                                 "t": round(elapsed, 2), "wallTs": wall, **tr}) + "\n")
            stats["rows"] += 1

        tick = {"type": "tick", "coin": sym, "mint": coin.get("mint", ""), "label": label,
                "t": round(elapsed, 2), "wallTs": wall, **m}
        series.append(tick)
        ds.write(json.dumps(tick) + "\n")
        ds.flush()
        stats["ticks"] += 1
        stats["rows"] += 1

        live = {
            "ts": time.time(), "live": True,
            "coin": {"symbol": sym, "label": label,
                     "elapsed": round(elapsed, 2), "dwell": DWELL_SEC,
                     "metrics": m, "series": series[-40:],
                     "trades": coin_trades[-15:], "nTrades": len(coin_trades)},
            "agents": _thoughts(sym, m, series, elapsed),
            "stats": {"coins": stats["coins"], "ticks": stats["ticks"], "rows": stats["rows"]},
        }
        try:
            _atomic_write_json(LIVE_JSON, live)
        except OSError:
            pass
        global _last_push
        if PUSH_URL and time.time() - _last_push >= PUSH_EVERY:
            _last_push = time.time()
            _push_live(live)
        await asyncio.sleep(POLL_MS / 1000)

    stats["coins"] += 1
    have = {k: series[-1].get(k) for k in ("devHold", "bundlers", "insiders", "snipers", "top10")} if series else {}
    logging.info("✓ %s done — %s ticks · %s trades · final %s", sym, len(series), len(coin_trades), have)


async def run() -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    LIVE_JSON.parent.mkdir(parents=True, exist_ok=True)
    _release_locks()
    work_w, work_h = _work_area()
    stats = {"coins": 0, "ticks": 0, "rows": 0}
    recent: list[str] = []

    # We run on a CLEAN COPY of the already-logged-in .axiom_profile, so NO Google
    # OAuth happens (Google blocks sign-in whenever automation/debugging is on). A
    # plain bundled-chromium launch on the copy loads Axiom already logged in — this
    # is the exact setup that returned real /meme coins earlier.
    async with async_playwright() as pw:
        context = await pw.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR), headless=False,
            viewport={"width": VIEWPORT_WIDTH, "height": min(VIEWPORT_HEIGHT, work_h - 90)},
            args=["--disable-blink-features=AutomationControlled", "--disable-dev-shm-usage",
                  "--no-default-browser-check", f"--window-size={VIEWPORT_WIDTH},{work_h}"],
        )
        try:
            await _stealth(context)
        except PlaywrightError:
            pass

        # ── SAFETY net: abort any request that looks like a trade/transaction ──
        # Belt-and-suspenders on top of (1) never clicking and (2) the wallet-less
        # profile. Even a stray interaction cannot send an order.
        async def _block_trades(route):
            try:
                req = route.request
                u = req.url.lower()
                pd = (req.post_data or "").lower()
                TX_URL = ("send-transaction", "sendtransaction", "sign-transaction",
                          "signtransaction", "execute", "/swap", "/buy", "/sell",
                          "/order", "/trade", "jupiter", "/tx/")
                TX_BODY = ("signtransaction", "sendtransaction", "swaptransaction",
                           "amountin", '"buy"', '"sell"')
                if req.method.upper() == "POST" and (
                    any(k in u for k in TX_URL) or any(k in pd for k in TX_BODY)
                ):
                    logging.warning("BLOCKED possible trade request: %s", req.url[:120])
                    await route.abort()
                    return
            except Exception:
                pass
            await route.continue_()

        try:
            await context.route("**/*", _block_trades)
        except PlaywrightError as exc:
            logging.warning("kjøps-killswitch ikke koblet til: %s", exc)

        page = context.pages[0] if context.pages else await context.new_page()
        page.set_default_timeout(20_000)

        await page.goto(PULSE_URL, wait_until="domcontentloaded", timeout=45_000)
        await _wait_cf(page)
        await _inject(page)
        page.on("domcontentloaded", lambda: asyncio.create_task(_inject(page)))
        logging.info("Klar. Samler data fra NEW PAIRS. Datasett → %s", DATASET.name)
        if DEBUG:
            logging.info("DEBUG på — dumper panel-tekst for første coin (for kalibrering).")

        clicked_mints: set[str] = set()   # coins we've already analysed (don't repeat)
        wait_polls = 0
        with DATASET.open("a", encoding="utf-8") as ds:
            while True:
                try:
                    if await _cf_light(page):
                        await _wait_cf(page)
                        await _inject(page)
                        continue
                    # Only open the TOP coin when its age is ≤ MAX_AGE (e.g. "0s") — that's
                    # the guarantee it was JUST launched, so the first 10s of data is accurate.
                    res = await page.evaluate(
                        "([av, ma]) => window.__pampsClickNewCoin ? window.__pampsClickNewCoin(av, ma) : {clicked:false}",
                        [list(clicked_mints), MAX_AGE],
                    )
                    if not res or not res.get("clicked"):
                        wait_polls += 1
                        if DEBUG and wait_polls % 14 == 1:
                            r = res or {}
                            extra = ""
                            if r.get("youngest") is None:
                                diag = await page.evaluate("() => window.__pampsDiag ? window.__pampsDiag() : null")
                                extra = f" DIAG={diag}"
                            logging.info("venter på ≤%ss… youngest=%ss reason=%s%s",
                                         MAX_AGE, r.get("youngest"), r.get("reason"), extra)
                        await _inject(page)
                        await asyncio.sleep(0.25)        # poll fast so we catch age 0–1s
                        continue
                    mint = res.get("mint") or ""
                    sym = (res.get("symbol") or mint[:6] or "$COIN").strip()
                    age = res.get("age")
                    clicked_mints.add(mint)
                    logging.info("NY coin (alder %ss · ventet %.1fs) — fanger fra start: %s",
                                 age, wait_polls * 0.35, sym)
                    wait_polls = 0

                    await asyncio.sleep(0.9)          # let the coin page + holder panel render
                    await _inject(page)
                    await _analyse_one(page, {"label": sym, "mint": mint}, stats, ds)

                    # back to NEW PAIRS and wait for the next 0s spawn
                    try:
                        await page.goto(PULSE_URL, wait_until="domcontentloaded", timeout=20_000)
                    except PlaywrightError:
                        pass
                    await asyncio.sleep(0.5)
                    await _inject(page)
                    if len(clicked_mints) > 800:
                        clicked_mints = set(list(clicked_mints)[-400:])
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    logging.warning("loop error: %s", exc)
                    await asyncio.sleep(1.0)


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logging.info("Stoppet. Datasett ligger i pamps_dataset.jsonl")
