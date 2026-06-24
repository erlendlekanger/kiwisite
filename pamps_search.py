"""PAMPS strategy search — continuously tests THOUSANDS of buy/sell rules on the
captured first-seconds data and surfaces the ones that survive out-of-sample.

A strategy = (entry time) + (entry filters) + (exit rule), e.g.
    "buy at 2s IF bundlers<=10% AND a >=2 SOL buy happened, sell on a 10% trail".
We enumerate thousands of these, evaluate each on the price (MC) curve with a
realistic round-trip cost, and split the coins into TRAIN (find candidates) and
TEST (validate). A rule is only reported if it's positive on BOTH.

THE OVERFITTING TRAP (read this): if you test N strategies, ~N*alpha of them look
good by pure luck. So the script also prints how many "winners" you'd expect by
chance. If survivors ~= chance, there is NO real edge yet — just noise. Trust a
rule only when it clearly beats the chance baseline AND holds on TEST AND has a
healthy sample size. Then paper-trade it before risking a cent.

Run:   py pamps_search.py
Loop:  PAMPS_LOOP=120 py pamps_search.py
Tune:  PAMPS_COST=0.05  PAMPS_MIN_N=15  PAMPS_HORIZON=25

RESEARCH OUTPUT ONLY — never places a trade.
"""
from __future__ import annotations

import json
import math
import os
import statistics as st
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATASET = HERE / "pamps_dataset.jsonl"
COST = float(os.environ.get("PAMPS_COST", "0.05"))
MIN_N = int(os.environ.get("PAMPS_MIN_N", "15"))
HORIZON = float(os.environ.get("PAMPS_HORIZON", "25"))
LOOP = float(os.environ.get("PAMPS_LOOP", "0"))
PUSH_URL = (os.environ.get("PAMPS_PUSH_URL") or "").rstrip("/")    # deployed Vercel base, optional
PUSH_SECRET = os.environ.get("PAMPS_PUSH_SECRET") or ""
METRICS = ("bundlers", "devHold", "top10", "snipers", "insiders", "vol")


# ── load + precompute per-coin sessions ──────────────────────────────────────
def load():
    ticks = defaultdict(list)
    trades = defaultdict(list)
    if not DATASET.exists():
        return []
    for ln in DATASET.open(encoding="utf-8"):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("type") == "trade":
            if "t" in r and r.get("mint"):
                trades[r["mint"]].append(r)
            continue
        if r.get("mcap") is None:
            continue
        key = r.get("mint") or r.get("coin") or "?"
        ticks[key].append((float(r.get("t", 0)), float(r["mcap"]), r))

    sessions = []
    for key, pts in ticks.items():
        pts.sort(key=lambda x: x[0])
        cur, last = [], -1.0
        for t, mc, r in pts:
            if t < last - 0.5 and cur:
                sessions.append((key, cur))
                cur = []
            cur.append((t, mc, r))
            last = t
        if cur:
            sessions.append((key, cur))

    out = []
    for key, series in sessions:
        if series[-1][0] < 3:
            continue
        out.append(Sess(key, series, trades.get(key, [])))
    return out


class Sess:
    __slots__ = ("mc0", "span", "msec", "fsec", "path", "bigbuy", "nbuys", "buyvol")

    def __init__(self, key, series, tr):
        self.mc0 = series[0][1]
        self.span = series[-1][0]
        top = int(self.span) + 1
        # mc + features snapshotted at each integer second (carry last seen)
        self.msec = {}
        self.fsec = {}
        cur = {k: None for k in METRICS}
        sec = 0
        for t, mc, r in series:
            for k in METRICS:
                v = r.get(k)
                if v is not None:
                    cur[k] = v
            while sec <= t and sec <= top:
                self.msec[sec] = mc
                self.fsec[sec] = dict(cur)
                sec += 1
        # downsampled price path (~0.4s) for trailing / take-profit exits
        self.path = []
        nxt = 0.0
        for t, mc, r in series:
            if t >= nxt:
                self.path.append((t, mc))
                nxt = t + 0.4
        if not self.path or self.path[-1][0] != series[-1][0]:
            self.path.append((series[-1][0], series[-1][1]))
        # cumulative trade features by integer second
        self.bigbuy = {}
        self.nbuys = {}
        self.buyvol = {}
        tr = sorted(tr, key=lambda x: x.get("t", 0))
        bb = nb = bv = 0.0
        ti = 0
        for s in range(0, top + 1):
            while ti < len(tr) and tr[ti].get("t", 0) <= s:
                x = tr[ti]
                if x.get("side") == "buy":
                    bb = max(bb, x.get("amt") or 0)
                    nb += 1
                    bv += x.get("amt") or 0
                ti += 1
            self.bigbuy[s], self.nbuys[s], self.buyvol[s] = bb, nb, bv

    def mc_at(self, t):
        return self.msec.get(min(int(t), int(self.span)))

    def feat(self, t, k):
        return self.fsec.get(min(int(t), int(self.span)), {}).get(k)


# ── filters + exits ──────────────────────────────────────────────────────────
def passes(s, B, filt):
    METRIC_LE = {"bundlers<=": "bundlers", "dev<=": "devHold", "top10<=": "top10",
                 "snipers<=": "snipers", "insiders<=": "insiders"}
    for kind, thr in filt:
        if kind in METRIC_LE:
            v = s.feat(B, METRIC_LE[kind])
            if v is None or v > thr:
                return False
        elif kind == "vol>=":
            v = s.feat(B, "vol")
            if v is None or v < thr:
                return False
        elif kind in ("mom>=", "mom<="):
            mb = s.mc_at(B)
            if not mb or not s.mc0:
                return False
            mom = mb / s.mc0
            if kind == "mom>=" and mom < thr:
                return False
            if kind == "mom<=" and mom > thr:
                return False
        elif kind == "bigbuy>=":
            if s.bigbuy.get(B, 0) < thr:
                return False
        elif kind == "nbuys>=":
            if s.nbuys.get(B, 0) < thr:
                return False
        elif kind == "buyvol>=":
            if s.buyvol.get(B, 0) < thr:
                return False
    return True


def ret(s, B, exit_):
    mb = s.mc_at(B)
    if not mb:
        return None
    kind, p = exit_
    if kind == "hold":
        if s.span < B + p - 0.3:
            return None
        ms = s.mc_at(B + p)
        return ms / mb - 1 - COST if ms else None
    # path-based (trailing / take-profit) from B to HORIZON
    if s.span < B + 1:
        return None
    peak = mb
    for t, mc in s.path:
        if t < B:
            continue
        if t > HORIZON:
            break
        peak = max(peak, mc)
        if kind == "trail" and mc <= peak * (1 - p):
            return mc / mb - 1 - COST
        if kind == "tp" and mc / mb - 1 >= p:
            return mc / mb - 1 - COST
    last = s.mc_at(min(HORIZON, s.span))
    return last / mb - 1 - COST if last else None


def summ(rets):
    rets = [r for r in rets if r is not None]
    if len(rets) < MIN_N:
        return None
    return {"n": len(rets), "mean": st.mean(rets),
            "win": sum(1 for x in rets if x > 0) / len(rets)}


# ── enumerate the strategy space ─────────────────────────────────────────────
def strategy_space():
    singles = []
    singles += [("bundlers<=", t) for t in (5, 10, 20)]
    singles += [("dev<=", t) for t in (5, 10, 20)]
    singles += [("top10<=", t) for t in (10, 20, 40)]
    singles += [("snipers<=", t) for t in (5, 15)]
    singles += [("vol>=", t) for t in (300, 800, 2000)]
    singles += [("mom>=", t) for t in (1.1, 1.3)]
    singles += [("mom<=", 0.95)]
    singles += [("bigbuy>=", t) for t in (1, 2, 5)]
    singles += [("nbuys>=", t) for t in (5, 10)]
    singles += [("buyvol>=", t) for t in (500, 2000)]

    fam = lambda f: f[0]
    filt_sets = [[]] + [[f] for f in singles]
    for i in range(len(singles)):           # curated pairs from different families
        for j in range(i + 1, len(singles)):
            if fam(singles[i]) != fam(singles[j]):
                filt_sets.append([singles[i], singles[j]])
    filt_sets = filt_sets[:140]             # cap to limit data-dredging

    entries = [0, 1, 2, 3]
    exits = ([("hold", h) for h in (1, 2, 3, 5, 8, 12, 20)]
             + [("trail", t) for t in (0.05, 0.1, 0.2)]
             + [("tp", t) for t in (0.1, 0.2, 0.4)])
    for B in entries:
        for fs in filt_sets:
            for ex in exits:
                if ex[0] == "hold" and B + ex[1] > HORIZON:
                    continue
                yield (B, fs, ex)


def fmt(B, fs, ex):
    f = " & ".join(f"{k}{thr}" for k, thr in fs) or "any"
    e = f"hold {ex[1]}s" if ex[0] == "hold" else (f"trail {int(ex[1]*100)}%" if ex[0] == "trail" else f"+{int(ex[1]*100)}% TP")
    return f"buy {B}s [{f}] -> {e}"


def run_once():
    sess = load()
    print(f"\n{'='*78}\nPAMPS strategy search | {time.strftime('%H:%M:%S')} | "
          f"cost {COST*100:.0f}% | min {MIN_N} coins/rule | horizon {HORIZON:.0f}s")
    print(f"coin sessions usable: {len(sess)}")
    if len(sess) < MIN_N * 4:
        print(f"! only {len(sess)} coins — far too few to trust ANY result. "
              f"This needs thousands. Let the collector run for days.")
    cut = int(len(sess) * 0.7)
    train, test = sess[:cut], sess[cut:]
    print(f"train {len(train)} / test {len(test)}\n")

    tested = 0
    cand = []   # positive on TRAIN
    for B, fs, ex in strategy_space():
        tested += 1
        tr = summ([ret(s, B, ex) for s in train if passes(s, B, fs)])
        if tr and tr["mean"] > 0:
            cand.append((B, fs, ex, tr))

    # validate candidates on TEST
    survivors = []
    for B, fs, ex, tr in cand:
        te = summ([ret(s, B, ex) for s in test if passes(s, B, fs)])
        if te and te["mean"] > 0:
            survivors.append((B, fs, ex, tr, te))
    survivors.sort(key=lambda x: -min(x[3]["mean"], x[4]["mean"]))

    # overfitting baseline: how many would pass on test by pure chance?
    expected_chance = len(cand) * 0.5     # ~half of train-positive rules flip positive on test by luck
    robust = len(survivors) > expected_chance * 1.2
    verdict = ("candidates beat chance — review further" if robust
               else "no robust edge yet — keep collecting")
    print(f"strategies tested: {tested}")
    print(f"positive on TRAIN: {len(cand)}")
    print(f"ALSO positive on TEST (survivors): {len(survivors)}  "
          f"(expected by chance ~{expected_chance:.0f})")
    print(">> " + verdict + "\n")
    print("-- top survivors (ranked by worst-of train/test mean) --")
    for B, fs, ex, tr, te in survivors[:12]:
        print(f"  {fmt(B, fs, ex)}")
        print(f"      train: n={tr['n']:>3} avg {tr['mean']*100:+6.1f}% win {tr['win']*100:3.0f}%"
              f"   |   test: n={te['n']:>3} avg {te['mean']*100:+6.1f}% win {te['win']*100:3.0f}%")
    if not survivors:
        print("  (none positive on both train and test)")

    # publish for the website: the 8 strongest candidate edges (by train mean),
    # each shown with its out-of-sample test numbers.
    topcand = sorted(cand, key=lambda x: -x[3]["mean"])[:8]
    top_json = []
    for B, fs, ex, tr in topcand:
        te = summ([ret(s, B, ex) for s in test if passes(s, B, fs)]) or {"n": 0, "mean": 0.0, "win": 0.0}
        top_json.append({"desc": fmt(B, fs, ex),
                         "trN": tr["n"], "trMean": round(tr["mean"], 4), "trWin": round(tr["win"], 2),
                         "teN": te["n"], "teMean": round(te["mean"], 4), "teWin": round(te["win"], 2)})
    out = {
        "ts": time.time(), "coins": len(sess), "tested": tested,
        "trainPos": len(cand), "survivors": len(survivors), "edges": len(top_json),
        "chance": round(expected_chance), "robust": robust, "verdict": verdict,
        "horizon": HORIZON, "cost": COST, "top": top_json,
    }
    try:
        sj = HERE / "pamps" / "search.json"
        tmp = sj.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(out), encoding="utf-8")
        os.replace(tmp, sj)
    except OSError:
        pass
    if PUSH_URL and PUSH_SECRET:                       # mirror to the deployed Vercel site
        try:
            req = urllib.request.Request(
                PUSH_URL + "/api/search", data=json.dumps(out).encode("utf-8"),
                headers={"Content-Type": "application/json", "X-Push-Secret": PUSH_SECRET},
                method="POST")
            urllib.request.urlopen(req, timeout=8).read()
        except Exception:
            pass


def main():
    if LOOP > 0:
        while True:
            run_once()
            time.sleep(LOOP)
    else:
        run_once()


if __name__ == "__main__":
    main()
