"""PAMPS analyzer -- search the captured first-seconds price (MC) curves for
buy/sell rules that would have been profitable WITHIN the analysis window.

We capture each fresh coin's market cap every ~100ms. MC is proportional to
price (pump.fun supply is fixed ~1B), so MC_sell / MC_buy is the gross return of
buying and selling inside the window. This script tries many entry/exit rules,
subtracts a realistic round-trip cost (fees + slippage), and validates the best
rules OUT OF SAMPLE (find on older coins, test on newer) so we don't fool
ourselves with patterns that are just noise.

Run:        py pamps_analyze.py
Loop it:    PAMPS_LOOP=60 py pamps_analyze.py     (re-run every 60s as data grows)
Tune:       PAMPS_COST=0.05  (round-trip cost) | PAMPS_MIN_N=20 (min coins per rule)

RESEARCH OUTPUT ONLY -- this never places a trade.
"""
from __future__ import annotations

import json
import os
import statistics as st
import time
from collections import defaultdict
from pathlib import Path

DATASET = Path(__file__).resolve().parent / "pamps_dataset.jsonl"
COST = float(os.environ.get("PAMPS_COST", "0.05"))      # round-trip fee + slippage haircut
MIN_N = int(os.environ.get("PAMPS_MIN_N", "20"))        # ignore rules with fewer coins
HORIZON = float(os.environ.get("PAMPS_HORIZON", "25"))  # seconds we trade within
LOOP = float(os.environ.get("PAMPS_LOOP", "0"))         # >0 = re-run every N seconds


def load_sessions() -> list[list[tuple]]:
    """Group tick rows into per-coin sessions: [(t, mcap, row), …] sorted by t."""
    by_key: dict[str, list[tuple]] = defaultdict(list)
    if not DATASET.exists():
        return []
    for line in DATASET.open(encoding="utf-8"):
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("type") not in (None, "tick"):   # skip trade rows
            continue
        mc = r.get("mcap")
        if mc is None:
            continue
        key = r.get("mint") or r.get("coin") or "?"
        by_key[key].append((float(r.get("t", 0)), float(mc), r))
    sessions = []
    for pts in by_key.values():
        pts.sort(key=lambda x: x[0])
        cur, last_t = [], -1.0
        for t, mc, r in pts:
            if t < last_t - 0.5 and cur:          # t reset -> same coin analysed again
                sessions.append(cur)
                cur = []
            cur.append((t, mc, r))
            last_t = t
        if cur:
            sessions.append(cur)
    return sessions


def mc_at(series, t):
    for (tt, mc, _) in series:
        if tt >= t:
            return mc
    return None


def span(series):
    return series[-1][0] if series else 0.0


def feat_at(series, t, key):
    """value of a feature (e.g. bundlers) at-or-before time t."""
    val = None
    for (tt, _, r) in series:
        if tt > t:
            break
        v = r.get(key)
        if v is not None:
            val = v
    return val


# ── strategies ───────────────────────────────────────────────────────────────
def ret_fixed(series, B, S):
    """buy at B, sell at S."""
    if span(series) < S - 0.3:
        return None
    mb, ms = mc_at(series, B), mc_at(series, S)
    if not mb or not ms:
        return None
    return ms / mb - 1 - COST


def ret_trail(series, B, trail, horizon):
    """buy at B, sell on a `trail` drop from the running peak, else at horizon."""
    if span(series) < B + 1:
        return None
    mb = mc_at(series, B)
    if not mb:
        return None
    peak, exit_mc = mb, None
    for (t, mc, _) in series:
        if t < B:
            continue
        if t > horizon:
            break
        peak = max(peak, mc)
        if mc <= peak * (1 - trail):
            exit_mc = mc
            break
    if exit_mc is None:
        exit_mc = mc_at(series, horizon) or series[-1][1]
    return exit_mc / mb - 1 - COST


def summ(rets):
    rets = [r for r in rets if r is not None]
    if not rets:
        return None
    return {"n": len(rets), "mean": st.mean(rets), "med": st.median(rets),
            "win": sum(1 for x in rets if x > 0) / len(rets)}


def line(tag, s):
    if not s:
        return f"  {tag:<26} (no samples)"
    return (f"  {tag:<26} n={s['n']:>4}  avg {s['mean']*100:+6.1f}%  "
            f"median {s['med']*100:+6.1f}%  win {s['win']*100:4.0f}%")


def run_once():
    sessions = load_sessions()
    usable = [s for s in sessions if span(s) >= 3]
    print(f"\n{'='*70}\nPAMPS analyzer | {time.strftime('%H:%M:%S')} | "
          f"round-trip cost {COST*100:.0f}% | min {MIN_N} coins/rule")
    print(f"coin sessions: {len(sessions)}  |  usable (>=3s): {len(usable)}")
    if len(usable) < MIN_N * 2:
        print(f"! only {len(usable)} coins -- need ~{MIN_N*2}+ for anything trustworthy. "
              "Let the collector run.")
    # out-of-sample split (sessions are roughly time-ordered as the file grows)
    cut = int(len(usable) * 0.7)
    train, test = usable[:cut], usable[cut:]
    print(f"train {len(train)} / test {len(test)}")

    # baseline: naive buy at 0s, sell at horizon
    print("\n-- baseline --")
    print(line("buy 0s -> sell 25s", summ([ret_fixed(s, 0, HORIZON) for s in usable])))

    # 1) fixed buy->sell grid, ranked on TRAIN, then shown out-of-sample on TEST
    grid = []
    buys = [0, 1, 2, 3, 4, 5, 7, 10]
    for B in buys:
        for S in (B + 1, B + 2, B + 3, B + 5, B + 8, B + 12, B + 18):
            if S > HORIZON:
                continue
            tr = summ([ret_fixed(s, B, S) for s in train])
            if tr and tr["n"] >= MIN_N:
                grid.append((B, S, tr))
    grid.sort(key=lambda x: -x[2]["mean"])
    print("\n-- best fixed buy->sell (ranked on TRAIN) with TEST validation --")
    for B, S, tr in grid[:6]:
        te = summ([ret_fixed(s, B, S) for s in test])
        print(line(f"buy {B}s -> sell {S}s  [train]", tr))
        print(line(f"                    [test ]", te))

    # 2) trailing-stop exits
    print("\n-- buy + trailing-stop exit (ranked on TRAIN) --")
    tgrid = []
    for B in (0, 1, 2, 3, 5):
        for trail in (0.05, 0.1, 0.15, 0.25):
            tr = summ([ret_trail(s, B, trail, HORIZON) for s in train])
            if tr and tr["n"] >= MIN_N:
                tgrid.append((B, trail, tr))
    tgrid.sort(key=lambda x: -x[2]["mean"])
    for B, trail, tr in tgrid[:5]:
        te = summ([ret_trail(s, B, trail, HORIZON) for s in test])
        print(line(f"buy {B}s | trail {int(trail*100)}% [train]", tr))
        print(line(f"                       [test ]", te))

    print("\nReading it: a rule is only interesting if it's positive on BOTH train AND "
          "test with a decent n. One good column = luck.")


def main():
    if LOOP > 0:
        while True:
            run_once()
            time.sleep(LOOP)
    else:
        run_once()


if __name__ == "__main__":
    main()
