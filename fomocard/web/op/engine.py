"""FOMOCARD engine: keyless Solana, pump.fun and Jupiter plumbing shared by the site
(op/core.py) and the desk (desk.py). Grown out of Handle's hd/engine.py.

Everything here is read-only or builds unsigned transactions, except the helpers
that take a Keypair (the desk). Nothing is broadcast while FOMOCARD_DRY=1 (default).
No fabricated numbers: an unreadable value is None, an empty one is 0.
"""
from __future__ import annotations

import base64
import json
import os
import struct
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from solders.instruction import AccountMeta, Instruction
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

ROOT = Path(__file__).resolve().parent
KEY_FILE = os.path.expanduser(os.environ.get("FOMOCARD_KEY_FILE", "~/fomocard_key.txt"))
def _dry_default() -> str:
    """Test mode unless op/config.json says otherwise. Kept in the config so the
    switch survives a restart, and so that turning it on is a deliberate edit
    rather than an environment variable someone forgets they set."""
    try:
        cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
        return "0" if cfg.get("checkout", {}).get("live") is True else "1"
    except (OSError, ValueError, AttributeError):
        return "1"


DRY = os.environ.get("FOMOCARD_DRY", _dry_default()).strip() not in ("0", "false", "no")

RPCS = [
    os.environ.get("SOLANA_RPC", "").strip() or "https://api.mainnet-beta.solana.com",
    "https://solana-rpc.publicnode.com",
]
PUMP_IPFS = "https://pump.fun/api/ipfs"
PUMP_COIN = "https://frontend-api-v3.pump.fun/coins/{mint}"
JUP_QUOTE = "https://lite-api.jup.ag/swap/v1/quote"
JUP_SWAP = "https://lite-api.jup.ag/swap/v1/swap"
JUP_PRICE = "https://lite-api.jup.ag/price/v3?ids={ids}"
JUP_TOKENS = "https://lite-api.jup.ag/tokens/v2/search?query={q}"

PUMP_PROGRAM = Pubkey.from_string("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P")
PUMPSWAP_PROGRAM = Pubkey.from_string("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA")
PFEE_PROGRAM = Pubkey.from_string("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ")
DBC_PROGRAM = Pubkey.from_string("dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN")
WSOL_MINT = Pubkey.from_string("So11111111111111111111111111111111111111112")
USDC_MINT = Pubkey.from_string("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v")
TOKEN_LEGACY = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022 = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
SYS_PROGRAM = Pubkey.from_string("11111111111111111111111111111111")
MEMO_PROGRAM = Pubkey.from_string("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr")
VAULT_RENT_LAMPORTS = 890_880
LAMPORTS = 1_000_000_000
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) FOMOCARD/1.0"}

_lock = threading.RLock()


# ---------------------------------------------------------------- http + rpc
def http_json(url: str, body: dict | None = None, timeout: int = 20, headers: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={**UA, **({"Content-Type": "application/json"} if data else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url.split('?')[0]} -> {exc.code}: {exc.read().decode('utf-8', 'ignore')[:200]}") from exc


def rpc(method: str, params: list, tries: int = 3):
    last = None
    for i in range(tries):
        url = RPCS[i % len(RPCS)]
        try:
            res = http_json(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=25)
            if "error" in res:
                raise RuntimeError(str(res["error"])[:240])
            return res.get("result")
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.4 * (i + 1))
    raise RuntimeError(f"rpc {method} failed: {last}")


def find_pda(seeds: list[bytes], program: Pubkey) -> Pubkey:
    return Pubkey.find_program_address(seeds, program)[0]


def ata(owner: Pubkey, mint: Pubkey, token_program: Pubkey = TOKEN_LEGACY) -> Pubkey:
    return find_pda([bytes(owner), bytes(token_program), bytes(mint)], ATA_PROGRAM)


def ata_create_idempotent_ix(payer: Pubkey, owner: Pubkey, mint: Pubkey, token_program: Pubkey = TOKEN_LEGACY) -> Instruction:
    return Instruction(ATA_PROGRAM, b"\x01", [
        AccountMeta(payer, True, True), AccountMeta(ata(owner, mint, token_program), False, True), AccountMeta(owner, False, False),
        AccountMeta(mint, False, False), AccountMeta(SYS_PROGRAM, False, False), AccountMeta(token_program, False, False)])


def system_transfer_ix(frm: Pubkey, to: Pubkey, lamports: int) -> Instruction:
    return Instruction(SYS_PROGRAM, struct.pack("<IQ", 2, lamports), [AccountMeta(frm, True, True), AccountMeta(to, False, True)])


def sync_native_ix(acct: Pubkey) -> Instruction:
    return Instruction(TOKEN_LEGACY, bytes([17]), [AccountMeta(acct, False, True)])


def close_account_ix(acct: Pubkey, dest: Pubkey, owner: Pubkey, token_program: Pubkey = TOKEN_LEGACY) -> Instruction:
    return Instruction(token_program, bytes([9]), [AccountMeta(acct, False, True), AccountMeta(dest, False, True), AccountMeta(owner, True, False)])


def transfer_checked_ix(src: Pubkey, mint: Pubkey, dst: Pubkey, owner: Pubkey, amount: int, decimals: int,
                        token_program: Pubkey = TOKEN_LEGACY) -> Instruction:
    return Instruction(token_program, bytes([12]) + struct.pack("<QB", amount, decimals), [
        AccountMeta(src, False, True), AccountMeta(mint, False, False), AccountMeta(dst, False, True), AccountMeta(owner, True, False)])


def burn_checked_ix(acct: Pubkey, mint: Pubkey, owner: Pubkey, amount: int, decimals: int, token_program: Pubkey = TOKEN_2022) -> Instruction:
    return Instruction(token_program, bytes([15]) + struct.pack("<QB", amount, decimals), [
        AccountMeta(acct, False, True), AccountMeta(mint, False, True), AccountMeta(owner, True, False)])


# ---------------------------------------------------------------- reads
def sol_balance(addr: str) -> float | None:
    try:
        return ((rpc("getBalance", [addr, {"commitment": "confirmed"}]) or {}).get("value", 0)) / LAMPORTS
    except RuntimeError:
        return None


_mint_cache: dict[str, dict] = {}


def mint_info(mint: str) -> dict | None:
    """{program, decimals, supply, extensions:[names]} for any SPL or Token-2022 mint. Cached (mints don't change shape)."""
    if mint in _mint_cache:
        return _mint_cache[mint]
    if mint == str(WSOL_MINT):
        _mint_cache[mint] = {"program": str(TOKEN_LEGACY), "decimals": 9, "supply": None, "extensions": []}
        return _mint_cache[mint]
    try:
        v = (rpc("getAccountInfo", [mint, {"encoding": "jsonParsed", "commitment": "confirmed"}]) or {}).get("value")
    except RuntimeError:
        return None
    if not v or not isinstance(v.get("data"), dict):
        return None
    info = v["data"]["parsed"]["info"]
    out = {"program": v["owner"], "decimals": int(info.get("decimals", 0)), "supply": int(info.get("supply") or 0),
           "extensions": [e.get("extension") for e in (info.get("extensions") or [])],
           "metadata": next((e.get("state") for e in (info.get("extensions") or []) if e.get("extension") == "tokenMetadata"), None)}
    _mint_cache[mint] = {k: v for k, v in out.items() if k != "metadata"}
    return out


def token_balance_raw(account: str) -> int | None:
    """Raw token amount of a token account; 0 when it does not exist; None on RPC failure."""
    try:
        v = (rpc("getAccountInfo", [account, {"encoding": "base64", "commitment": "confirmed"}]) or {}).get("value")
    except RuntimeError:
        return None
    if not v:
        return 0
    raw = base64.b64decode(v["data"][0])
    return int.from_bytes(raw[64:72], "little") if len(raw) >= 72 else 0


def vault_balances(addrs: list[str]) -> dict[str, int | None]:
    """Claimable raw amount per fee vault in one RPC per 100 addresses. System-owned vault:
    lamports above the rent floor. Token account (any token program): its raw amount.
    Missing account = 0, RPC failure = None."""
    out: dict[str, int | None] = {a: None for a in addrs}
    for i in range(0, len(addrs), 100):
        chunk = addrs[i:i + 100]
        try:
            res = rpc("getMultipleAccounts", [chunk, {"encoding": "base64", "commitment": "confirmed"}])
        except RuntimeError:
            continue
        for a, acc in zip(chunk, (res or {}).get("value") or []):
            if not acc:
                out[a] = 0
                continue
            try:
                if acc.get("owner") in (str(TOKEN_LEGACY), str(TOKEN_2022)):
                    raw = base64.b64decode(acc["data"][0])
                    out[a] = int.from_bytes(raw[64:72], "little") if len(raw) >= 72 else 0
                else:
                    out[a] = max(0, int(acc.get("lamports") or 0) - VAULT_RENT_LAMPORTS)
            except Exception:  # noqa: BLE001
                out[a] = None
    return out


def prices_usd(mints: list[str]) -> dict[str, float | None]:
    out: dict[str, float | None] = {m: None for m in mints}
    for i in range(0, len(mints), 50):
        chunk = mints[i:i + 50]
        try:
            d = http_json(JUP_PRICE.format(ids=",".join(chunk)), timeout=10)
        except RuntimeError:
            continue
        for m in chunk:
            p = (d.get(m) or {}).get("usdPrice")
            try:
                out[m] = float(p) if p is not None else None
            except (TypeError, ValueError):
                out[m] = None
    return out


def token_search(q: str) -> list[dict]:
    try:
        d = http_json(JUP_TOKENS.format(q=urllib.parse.quote(q)), timeout=10)
    except RuntimeError:
        return []
    return d if isinstance(d, list) else []


def pump_coin(mint: str) -> dict | None:
    try:
        return http_json(PUMP_COIN.format(mint=mint), timeout=12)
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------- tx
def simulate(tx: VersionedTransaction) -> dict:
    res = rpc("simulateTransaction", [base64.b64encode(bytes(tx)).decode(),
                                      {"encoding": "base64", "sigVerify": False, "replaceRecentBlockhash": True, "commitment": "processed"}])
    v = (res or {}).get("value") or {}
    return {"ok": v.get("err") is None, "err": v.get("err"), "logs": (v.get("logs") or [])[-14:], "units": v.get("unitsConsumed")}


def send_tx(signed: VersionedTransaction, skip_preflight: bool = True) -> str:
    return rpc("sendTransaction", [base64.b64encode(bytes(signed)).decode(),
                                   {"encoding": "base64", "skipPreflight": skip_preflight, "maxRetries": 3,
                                    "preflightCommitment": "confirmed"}])   # blockhash() is fetched at confirmed; the default (finalized) rejects it


def wait_confirmed(sig: str, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = (rpc("getSignatureStatuses", [[sig]]).get("value") or [None])[0]
            if st:
                if st.get("err"):
                    raise RuntimeError(f"tx failed on-chain: {st['err']}")
                if st.get("confirmationStatus") in ("confirmed", "finalized"):
                    return True
        except RuntimeError as exc:
            if "failed on-chain" in str(exc):
                raise
        time.sleep(2)
    return False


def get_tx(sig: str, tries: int = 5) -> dict | None:
    for _ in range(tries):
        try:
            tx = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
        except RuntimeError:
            tx = None
        if tx:
            return tx
        time.sleep(1.5)
    return None


def tx_keys(tx: dict) -> list[str]:
    keys = [k if isinstance(k, str) else k.get("pubkey") for k in tx["transaction"]["message"]["accountKeys"]]
    la = (tx.get("meta") or {}).get("loadedAddresses") or {}
    return keys + la.get("writable", []) + la.get("readonly", [])


def tx_sol_delta(tx: dict, addr: str) -> int | None:
    """Lamport change of `addr` inside a confirmed transaction (fee added back for the fee payer)."""
    keys = tx_keys(tx)
    if addr not in keys:
        return None
    i = keys.index(addr)
    d = tx["meta"]["postBalances"][i] - tx["meta"]["preBalances"][i]
    return d + (tx["meta"].get("fee", 0) if i == 0 else 0)


def tx_token_delta(tx: dict, owner: str, mint: str) -> int:
    """Raw token change for (owner, mint) inside a confirmed transaction."""
    def total(rows):
        return sum(int(r["uiTokenAmount"]["amount"]) for r in rows or [] if r.get("owner") == owner and r.get("mint") == mint)
    m = tx.get("meta") or {}
    return total(m.get("postTokenBalances")) - total(m.get("preTokenBalances"))


def tx_touches(sig: str, *addrs: str) -> bool | None:
    tx = get_tx(sig, tries=3)
    if not tx:
        return None
    return all(a in tx_keys(tx) for a in addrs) and not (tx.get("meta") or {}).get("err")


def block_height() -> int | None:
    try:
        return int(rpc("getBlockHeight", [{"commitment": "confirmed"}]))
    except Exception:  # noqa: BLE001
        return None


def blockhash() -> tuple[str, int | None]:
    v = rpc("getLatestBlockhash", [{"commitment": "confirmed"}])["value"]
    return v["blockhash"], v.get("lastValidBlockHeight")


def partial_sign(msg, signers: list[Keypair]) -> VersionedTransaction:
    """Signs a MessageV0 with the given keypairs and leaves the other slots empty for the wallet.
    The signature must cover the versioned serialization (0x80 prefix + message)."""
    from solders.message import to_bytes_versioned
    from solders.signature import Signature
    sigs = [Signature.default()] * msg.header.num_required_signatures
    keys = list(msg.account_keys)
    raw = to_bytes_versioned(msg)
    for kp in signers:
        sigs[keys.index(kp.pubkey())] = kp.sign_message(raw)
    return VersionedTransaction.populate(msg, sigs)


# ---------------------------------------------------------------- jupiter
# Oracle-quoted prop AMMs: their price is only valid for a few slots, so a swap that waits on a wallet prompt
# lands stale and fails (2026-09-16: Quantum, custom error 0xe on a GBP launch). Excluded for user-signed swaps.
PROP_AMMS = ("Quantum", "HumidiFi", "SolFi", "SolFi V2", "TesseraV", "GoonFi V2", "ZeroFi", "Obric V2", "BisonFi",
             "AlphaQ", "Aquifer", "Scorch", "WhaleStreet", "Hadron", "JupiterRfqV2")


def jup_quote(input_mint: str, output_mint: str, amount: int, slippage_bps: int = 300, mode: str = "ExactIn",
              exclude_dexes: tuple | list = ()) -> dict:
    q = {"inputMint": input_mint, "outputMint": output_mint, "amount": str(int(amount)), "slippageBps": str(slippage_bps),
         "swapMode": mode, "restrictIntermediateTokens": "true"}
    if exclude_dexes:
        q["excludeDexes"] = ",".join(exclude_dexes)
    # The public Jupiter endpoint rate-limits, and a shopper mid-checkout should not
    # be shown a 429. Back off briefly and try again before giving up.
    last = None
    for attempt in range(3):
        try:
            d = http_json(JUP_QUOTE + "?" + urllib.parse.urlencode(q), timeout=15)
        except RuntimeError as exc:
            last = exc
            if "429" not in str(exc):
                raise
            time.sleep(0.8 * (attempt + 1))
            continue
        if not d.get("outAmount"):
            raise RuntimeError(f"no Jupiter route {input_mint[:6]} -> {output_mint[:6]}: {str(d)[:160]}")
        return d
    raise RuntimeError(f"Jupiter is rate limiting us, try again in a moment ({str(last)[:80]})")


def jup_swap_tx(quote: dict, user: str, priority_lamports: int = 200_000) -> VersionedTransaction:
    d = http_json(JUP_SWAP, {"quoteResponse": quote, "userPublicKey": user, "wrapAndUnwrapSol": True, "dynamicComputeUnitLimit": True,
                             "prioritizationFeeLamports": {"priorityLevelWithMaxLamports": {"maxLamports": priority_lamports, "priorityLevel": "high"}}},
                  timeout=20)
    if not d.get("swapTransaction"):
        raise RuntimeError(f"Jupiter swap build failed: {str(d)[:160]}")
    return VersionedTransaction.from_bytes(base64.b64decode(d["swapTransaction"]))


# ---------------------------------------------------------------- metadata
def _multipart(fields: dict, fname: str, ctype: str, data: bytes) -> tuple[str, bytes]:
    boundary = "----multipad" + uuid.uuid4().hex
    out = bytearray()
    for k, v in fields.items():
        out += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
    out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{fname}\"\r\n"
            f"Content-Type: {ctype}\r\n\r\n").encode() + data + f"\r\n--{boundary}--\r\n".encode()
    return boundary, bytes(out)


def upload_metadata(name: str, symbol: str, description: str, image: bytes, image_type: str,
                    website: str = "", twitter: str = "", telegram: str = "") -> str:
    """Metadata URI via pump.fun's keyless IPFS endpoint (the same one pump.fun's own create page uses)."""
    fields = {"name": name, "symbol": symbol, "description": description, "twitter": twitter,
              "telegram": telegram, "website": website, "showName": "true"}
    boundary, body = _multipart(fields, "image." + image_type.split("/")[-1], image_type, image)
    req = urllib.request.Request(PUMP_IPFS, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}", **UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        res = json.loads(r.read().decode("utf-8"))
    uri = res.get("metadataUri") or (res.get("metadata") or {}).get("uri")
    if not uri:
        raise RuntimeError(f"pump ipfs: {str(res)[:120]}")
    return uri


# ---------------------------------------------------------------- key
def load_keypair() -> Keypair | None:
    raw = os.environ.get("FOMOCARD_KEY", "").strip()
    if not raw and os.path.isfile(KEY_FILE):
        lines = [ln.strip() for ln in Path(KEY_FILE).read_text(encoding="utf-8-sig").splitlines()   # Notepad adds a BOM
                 if ln.strip() and not ln.strip().startswith("#")]
        raw = "".join(lines) if lines and lines[0].startswith("[") else (lines[0] if lines else "")
    if not raw:
        return None
    if raw.startswith("["):
        return Keypair.from_bytes(bytes(json.loads(raw)))
    return Keypair.from_base58_string(raw)
