"""Shared state for FOMOCARD: Upstash Redis over REST on Vercel, a JSON-file
emulation of the same commands for local development.

Only a small Redis subset is used, so the file backend is tiny:
  GET SET(NX/EX) GETDEL DEL INCR EXPIRE RPUSH LRANGE LLEN LTRIM
  HGET HSET HGETALL HINCRBYFLOAT SADD SREM SMEMBERS SISMEMBER SCARD
Keys are prefixed (default "fc:") so one KV store can host several apps.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from pathlib import Path

PREFIX = os.environ.get("OP_PREFIX", "fc:")


class UpstashKV:
    def __init__(self, url: str, token: str):
        self.url, self.token = url.rstrip("/"), token

    def _post(self, path: str, body) -> object:
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"},
                                     method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))

    def cmd(self, *args):
        data = self._post("", [str(a) for a in args])
        if isinstance(data, dict) and data.get("error"):
            raise RuntimeError("KV error: " + str(data["error"]))
        return data.get("result") if isinstance(data, dict) else None

    def pipeline(self, cmds: list[list]) -> list:
        data = self._post("/pipeline", [[str(a) for a in c] for c in cmds])
        out = []
        for d in data:
            if isinstance(d, dict) and d.get("error"):
                raise RuntimeError("KV error: " + str(d["error"]))
            out.append(d.get("result") if isinstance(d, dict) else None)
        return out


class FileKV:
    """Local stand-in with the same command surface. Single JSON file shared by the site, the desk and the admin
    dashboard, so every read-modify-write runs under a lock FILE (a thread lock only covers one process).

    2026-09-18: the old version treated ANY read error as "no state yet" and saved an empty state over the real
    one. With three processes on the file, one read landed while another was replacing it, and the whole ledger
    was wiped. Now: a missing file is the only empty state, an unreadable file raises, a write that would shrink
    the state to almost nothing is refused, and a copy is kept once a minute."""

    LOCK_WAIT_S, LOCK_STALE_S = 20.0, 30.0

    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.lockfile = path.with_suffix(".lock")
        self._depth = 0
        self._last_backup = 0.0

    def _acquire(self) -> None:
        self.lock.acquire()
        self._depth += 1
        if self._depth > 1:
            return
        deadline = time.time() + self.LOCK_WAIT_S
        while True:
            try:
                fd = os.open(str(self.lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return
            except FileExistsError:
                try:
                    if time.time() - self.lockfile.stat().st_mtime > self.LOCK_STALE_S:
                        self.lockfile.unlink()                       # left behind by a process that died
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    self._depth -= 1
                    self.lock.release()
                    raise RuntimeError("state file is locked by another process") from None
                time.sleep(0.02)
            except PermissionError:                                  # Windows: the file is being deleted right now
                time.sleep(0.02)

    def _release(self) -> None:
        self._depth -= 1
        if self._depth == 0:
            try:
                self.lockfile.unlink()
            except OSError:
                pass
        self.lock.release()

    def _load(self) -> dict:
        for attempt in range(40):
            try:
                raw = self.path.read_text(encoding="utf-8")
            except FileNotFoundError:
                return {"kv": {}, "exp": {}, "lists": {}, "hashes": {}, "sets": {}}
            except OSError:
                time.sleep(0.05)
                continue
            try:
                d = json.loads(raw)
                if isinstance(d, dict) and all(k in d for k in ("kv", "exp", "lists", "hashes", "sets")):
                    return d
            except ValueError:
                pass
            time.sleep(0.05)
        raise RuntimeError(f"state file {self.path} is unreadable; refusing to start from an empty state")

    def _save(self, d: dict) -> None:
        data = json.dumps(d, ensure_ascii=False, allow_nan=False)
        try:
            old = self.path.stat().st_size
        except OSError:
            old = 0
        if old > 4000 and len(data.encode("utf-8")) < old * 0.2:
            raise RuntimeError("refusing to write: the new state is under 20% of the size of the one on disk")
        if old and time.time() - self._last_backup > 60:
            try:
                slot = int(time.time() // 60) % 10               # ten rolling copies, one minute apart
                self.path.with_name(f"{self.path.stem}.bak{slot}.json").write_bytes(self.path.read_bytes())
                self._last_backup = time.time()
            except OSError:
                pass
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(data, encoding="utf-8")
        for attempt in range(40):
            try:
                tmp.replace(self.path)
                return
            except PermissionError:                                  # Windows: a reader has it open for a moment
                time.sleep(0.05)
        raise RuntimeError("could not replace the state file")

    def _alive(self, d: dict, k: str) -> bool:
        exp = d["exp"].get(k)
        if exp and exp < time.time():
            d["kv"].pop(k, None)
            d["exp"].pop(k, None)
            return False
        return k in d["kv"]

    READ_OPS = {"GET", "LRANGE", "LLEN", "HGET", "HGETALL", "SMEMBERS", "SISMEMBER", "SCARD", "EXISTS"}

    def cmd(self, *args):
        self._acquire()
        try:
            d = self._load()
            a = [str(x) for x in args]
            res = self._exec(d, a)
            if a[0].upper() not in self.READ_OPS:
                self._save(d)
            return res
        finally:
            self._release()

    def pipeline(self, cmds: list[list]) -> list:
        self._acquire()
        try:
            d = self._load()
            rows = [[str(a) for a in c] for c in cmds]
            out = [self._exec(d, c) for c in rows]
            if any(c[0].upper() not in self.READ_OPS for c in rows):
                self._save(d)
            return out
        finally:
            self._release()

    def _exec(self, d: dict, a: list[str]):
        op = a[0].upper()
        if op == "GET":
            return d["kv"].get(a[1]) if self._alive(d, a[1]) else None
        if op == "SET":
            k, v, opts = a[1], a[2], [x.upper() for x in a[3:]]
            if "NX" in opts and self._alive(d, k):
                return None
            d["kv"][k] = v
            d["exp"].pop(k, None)
            if "EX" in opts:
                d["exp"][k] = time.time() + float(a[3 + opts.index("EX") + 1])
            return "OK"
        if op == "GETDEL":
            v = d["kv"].pop(a[1], None) if self._alive(d, a[1]) else None
            d["exp"].pop(a[1], None)
            return v
        if op == "DEL":
            n = 0
            for k in a[1:]:
                n += int(k in d["kv"] or k in d["lists"] or k in d["hashes"] or k in d["sets"])
                d["kv"].pop(k, None); d["lists"].pop(k, None); d["hashes"].pop(k, None); d["sets"].pop(k, None); d["exp"].pop(k, None)
            return n
        if op == "INCR":
            v = int(d["kv"].get(a[1], "0")) + 1 if self._alive(d, a[1]) else 1
            d["kv"][a[1]] = str(v)
            return v
        if op == "EXPIRE":
            d["exp"][a[1]] = time.time() + float(a[2])
            return 1
        if op == "RPUSH":
            lst = d["lists"].setdefault(a[1], [])
            lst.extend(a[2:])
            return len(lst)
        if op == "LRANGE":
            lst = d["lists"].get(a[1], [])
            start, stop = int(a[2]), int(a[3])
            if stop == -1:
                return lst[start:]
            return lst[start:stop + 1]
        if op == "LLEN":
            return len(d["lists"].get(a[1], []))
        if op == "LTRIM":
            lst = d["lists"].get(a[1], [])
            start, stop = int(a[2]), int(a[3])
            d["lists"][a[1]] = lst[start:] if stop == -1 else lst[start:stop + 1]
            return "OK"
        if op == "HGET":
            return d["hashes"].get(a[1], {}).get(a[2])
        if op == "HSET":
            h = d["hashes"].setdefault(a[1], {})
            new = 0
            for i in range(2, len(a) - 1, 2):
                new += int(a[i] not in h)
                h[a[i]] = a[i + 1]
            return new
        if op == "HGETALL":
            h = d["hashes"].get(a[1], {})
            out = []
            for k, v in h.items():
                out += [k, v]
            return out
        if op == "HINCRBYFLOAT":
            h = d["hashes"].setdefault(a[1], {})
            v = float(h.get(a[2], "0")) + float(a[3])
            h[a[2]] = repr(v)
            return h[a[2]]
        if op == "SADD":
            s = d["sets"].setdefault(a[1], [])
            n = 0
            for m in a[2:]:
                if m not in s:
                    s.append(m); n += 1
            return n
        if op == "EXISTS":
            return int(self._alive(d, a[1]) or a[1] in d["hashes"] or a[1] in d["sets"] or a[1] in d["lists"])
        if op == "SREM":
            s = d["sets"].get(a[1], [])
            n = sum(1 for m in a[2:] if m in s)
            d["sets"][a[1]] = [m for m in s if m not in a[2:]]
            return n
        if op == "SMEMBERS":
            return list(d["sets"].get(a[1], []))
        if op == "SISMEMBER":
            return int(a[2] in d["sets"].get(a[1], []))
        if op == "SCARD":
            return len(d["sets"].get(a[1], []))
        raise RuntimeError(f"FileKV: unsupported {op}")


_store = None


def store():
    global _store
    if _store is not None:
        return _store
    # the project own Upstash store (fomocard_ prefix) wins over a shared one
    url = (os.environ.get("fomocard_KV_REST_API_URL") or os.environ.get("KV_REST_API_URL")
           or os.environ.get("UPSTASH_REDIS_REST_URL") or "").strip()
    token = (os.environ.get("fomocard_KV_REST_API_TOKEN") or os.environ.get("KV_REST_API_TOKEN")
             or os.environ.get("UPSTASH_REDIS_REST_TOKEN") or "").strip()
    if url and token:
        _store = UpstashKV(url, token)
    else:
        path = Path(os.environ.get("OP_STATE_FILE") or (Path(__file__).resolve().parent.parent / "local_state.json"))
        _store = FileKV(path)
    return _store


def is_kv() -> bool:
    return isinstance(store(), UpstashKV)


def key(name: str) -> str:
    return PREFIX + name
