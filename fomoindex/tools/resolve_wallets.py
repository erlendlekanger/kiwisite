"""Find the wallet each fomo trader actually trades from, most popular first, so FOMOINDEX mirrors the right wallet.

fomo's profile `address` is not that wallet. FOMOBOT's fomo.trade_wallet() finds it: it takes the trader's balances
from fomo and matches an exact token amount to its token account on the chain (or, failing that, their newest buy).
The result is stored on the shared directory record (fp:fomo:handle:<h>.trade_wallet), which FOMOINDEX reads.

Needs a live fomo session (fp:fomo:session). Renew it with:
    py fomopad/tools/fomo_session.py --token <privy:token> --refresh <privy:refresh_token>

    py fomoindex/tools/resolve_wallets.py                # the 300 most popular without a trading wallet
    py fomoindex/tools/resolve_wallets.py --max 2000 --delay 0.4
    py fomoindex/tools/resolve_wallets.py --handles unipcs frankdegods
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_env() -> None:
    # FOMOINDEX's store is the same Upstash database as the fomo directory (fp:)
    env = Path.home() / "fomoindex.env"
    for line in env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))
    os.environ.setdefault("COPYBOT_FOMO_KV_REST_API_URL", os.environ.get("FI_KV_REST_API_URL", ""))
    os.environ.setdefault("COPYBOT_FOMO_KV_REST_API_TOKEN", os.environ.get("FI_KV_REST_API_TOKEN", ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--delay", type=float, default=0.6)
    ap.add_argument("--handles", nargs="*")
    a = ap.parse_args()
    load_env()
    sys.path.insert(0, str(ROOT / "copybot" / "api"))
    import fomo  # noqa: E402  (FOMOBOT's fomo client)

    st = fomo.session_status() if hasattr(fomo, "session_status") else None
    kv = fomo._store()
    order = [h.lower() for h in a.handles] if a.handles else json.loads(kv.cmd("GET", "fi:popular") or "[]")
    done = found = 0
    for h in order:
        if found >= a.max:
            break
        p = json.loads(kv.cmd("GET", "fp:fomo:handle:" + h) or "null")
        if not p or (p.get("trade_wallet") and not a.handles):
            continue
        done += 1
        try:
            r = fomo.trade_wallet(p)
        except Exception as e:  # noqa: BLE001
            r = {"ok": False, "error": str(e)}
        if r.get("down"):
            print(f"stopped: fomo answered '{r.get('error')}'. Renew the fomo session (see the top of this file).")
            break
        if r.get("ok"):
            found += 1
            print(f"{h:24} {r['wallet']}  ({r.get('from')})")
        else:
            print(f"{h:24} -  {r.get('error', '')[:80]}")
        time.sleep(a.delay)
    print(f"checked {done}, trading wallets found {found}")
    if st is not None:
        print("session:", st)


if __name__ == "__main__":
    main()
