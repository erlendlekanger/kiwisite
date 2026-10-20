"""Turn fomo_balances.json (saved by the Console line from make_console_line.py) into confirmed trading wallets.

For each trader, fomo's balances give each token and its exact amount. The one token account on the chain holding exactly
that amount of that token belongs to the wallet they trade from (FOMOBOT's matching, fomo._owners_near). Two holdings
that agree, or one holding with a single owner, confirm it. The wallet is stored on the shared directory record
(fp:fomo:handle:<h>.trade_wallet), which FOMOINDEX mirrors from.

    py fomoindex/tools/match_balances.py [path to fomo_balances.json]   (default: the newest one in Downloads)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    for line in (Path.home() / "fomoindex.env").read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))
    os.environ.setdefault("COPYBOT_FOMO_KV_REST_API_URL", os.environ.get("FI_KV_REST_API_URL", ""))
    os.environ.setdefault("COPYBOT_FOMO_KV_REST_API_TOKEN", os.environ.get("FI_KV_REST_API_TOKEN", ""))


def holdings(r: dict, fomo) -> list[tuple[str, float]]:
    # the same reading as fomo.holdings(): Solana tokens, the two-decimal shiftedBalance, no SOL or stables
    body = r.get("responseObject") if isinstance(r.get("responseObject"), dict) else r.get("data") if isinstance(r.get("data"), dict) else r
    out = []
    for b in (body or {}).get("balances") or []:
        bal = b.get("balance") or {}
        mint = bal.get("tokenAddress") or ""
        try:
            human = float(bal.get("shiftedBalance"))
        except (TypeError, ValueError):
            continue
        if human >= 1 and fomo._is_sol(mint) and mint not in fomo.STABLE_OR_SOL:
            out.append((mint, human))
    return out


def main() -> None:
    load_env()
    sys.path.insert(0, str(ROOT / "copybot" / "api"))
    import fomo  # noqa: E402  (FOMOBOT's fomo client: matching and the shared store)

    if len(sys.argv) > 1:
        path = Path(sys.argv[1])
    else:
        found = sorted((Path.home() / "Downloads").glob("fomo_balances*.json"), key=lambda p: p.stat().st_mtime)
        if not found:
            sys.exit("no fomo_balances.json in Downloads yet")
        path = found[-1]
    data = json.loads(path.read_text(encoding="utf-8"))
    print(f"{path.name}: {len(data)} traders")
    kv = fomo._store()
    got = none = empty = 0
    done = 0
    for h, row in data.items():
        if json.loads(kv.cmd("GET", "fp:fomo:handle:" + h.lower()) or "{}").get("trade_wallet"):
            done += 1                      # confirmed already (an earlier run, or FOMOBOT)
            continue
        held = holdings(row.get("r") or {}, fomo)
        if not held:
            empty += 1
            print(f"{h:24} -  holds no tokens on fomo right now, nothing to match on")
            continue
        votes: dict[str, int] = {}
        for mint, human in sorted(held, key=lambda x: -x[1])[:6]:
            for w in fomo._owners_near(mint, human):
                votes[w] = votes.get(w, 0) + 1
            if votes and max(votes.values()) >= 2:
                break
            time.sleep(0.3)
        best = max(votes.items(), key=lambda kv_: kv_[1]) if votes else None
        if best and (best[1] >= 2 or len(votes) == 1):
            key = "fp:fomo:handle:" + h.lower()
            rec = json.loads(kv.cmd("GET", key) or "null") or {"handle": h}
            rec.update({"trade_wallet": best[0], "trade_wallet_at": int(time.time())})
            kv.cmd("SET", key, json.dumps(rec, separators=(",", ":")))
            got += 1
            print(f"{h:24} {best[0]}  ({best[1]} holding{'s' if best[1] > 1 else ''} agree)")
        else:
            none += 1
            print(f"{h:24} -  no single wallet matched ({len(votes)} candidates)")
    print(f"\ntrading wallets confirmed: {got}, unmatched: {none}, holding nothing: {empty}, already confirmed: {done}")


if __name__ == "__main__":
    main()
