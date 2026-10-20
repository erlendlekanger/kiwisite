// Storage on Upstash Redis (REST), like the other projects: FOMOINDEX's own data under the "fi:" prefix, and the
// fomo trader directory (about 6 000 usernames with wallet and avatar, crawled by FOMOPAD and read by FOMOFANTASY)
// under "fp:". Env: FI_KV_REST_API_URL / FI_KV_REST_API_TOKEN (falls back to KV_REST_API_URL / _TOKEN).
//
//   fi:users                 hash  wallet -> {created_at, last_seen}
//   fi:nonce:<nonce>         string wallet, 15 min
//   fi:ix                    hash  id -> index record
//   fi:owner:<wallet>        set   index ids
//   fi:snap:<id>             list  NAV snapshots, oldest first (last 2000)
//   fi:trades:<id>           list  trades, newest first (last 500);  fi:sigs:<id> set of recorded signatures
//   fi:events:<id|_>         list  events, newest first (last 200)
//   fi:tok                   hash  mint -> token info {symbol, name, icon, decimals, liquidity_usd, price_usd, ..., updated_at}
//   fi:trader:<handle>       string our overlay on a trader: rank, pnl, positions, active, a wallet added by hand
//   fi:lb                    string FOMO's 7-day leaderboard order [{handle, rank, pnl_7d}], written by sync-traders
//   fp:fomo:handles          set   every fomo username (lower case)       (read only)
//   fp:fomo:handle:<handle>  string {handle, name, avatar, wallet, id}    (read only)
//   fp:fomo:session          string the shared FOMO (Privy) session     (read; refreshed by FOMOPAD/FOMOFANTASY)

const P = 'fi:';
const env = (a, b) => (process.env[a] || process.env[b] || '').trim();

export async function kv(...cmd) {
  const url = env('FI_KV_REST_API_URL', 'KV_REST_API_URL'), tok = env('FI_KV_REST_API_TOKEN', 'KV_REST_API_TOKEN');
  if (!url || !tok) throw new Error('FI_KV_REST_API_URL is not set');
  const r = await fetch(url, { method: 'POST', headers: { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' }, body: JSON.stringify(cmd.map(String)) });
  const j = await r.json().catch(() => ({}));
  if (j.error) throw new Error('KV: ' + j.error);
  return j.result;
}
export async function pipe(cmds) {
  if (!cmds.length) return [];
  const url = env('FI_KV_REST_API_URL', 'KV_REST_API_URL'), tok = env('FI_KV_REST_API_TOKEN', 'KV_REST_API_TOKEN');
  if (!url || !tok) throw new Error('FI_KV_REST_API_URL is not set');
  const out = [];
  for (let i = 0; i < cmds.length; i += 200) {
    const r = await fetch(url.replace(/\/$/, '') + '/pipeline', { method: 'POST', headers: { Authorization: 'Bearer ' + tok, 'Content-Type': 'application/json' }, body: JSON.stringify(cmds.slice(i, i + 200).map((c) => c.map(String))) });
    const j = await r.json();
    for (const x of j) out.push(x.error ? null : x.result);
  }
  return out;
}
const J = (s) => { try { return s ? JSON.parse(s) : null; } catch (e) { return null; } };
const now = () => new Date().toISOString();

export async function ping() { return (await kv('PING')) === 'PONG'; }

/* ---------------------------------------------------------------- events */
export async function log(index_id, level, message, data) {
  try {
    const k = P + 'events:' + (index_id || '_');
    await pipe([['LPUSH', k, JSON.stringify({ ts: now(), level, message, data: data ?? null })], ['LTRIM', k, 0, 199]]);
  } catch (e) { /* logging never fails the request */ }
}
export async function events(id, n = 50) { return ((await kv('LRANGE', P + 'events:' + id, 0, n - 1)) || []).map(J).filter(Boolean); }

/* ---------------------------------------------------------------- users and sign-in nonces */
export async function touchUser(wallet) {
  const cur = J(await kv('HGET', P + 'users', wallet));
  await kv('HSET', P + 'users', wallet, JSON.stringify({ created_at: cur?.created_at || now(), last_seen: now() }));
}
export async function putNonce(nonce, wallet) { await kv('SET', P + 'nonce:' + nonce, wallet, 'EX', 900); }
export async function takeNonce(nonce, wallet) {
  const got = await kv('GETDEL', P + 'nonce:' + nonce);
  return !!got && got === wallet;
}

/* ---------------------------------------------------------------- indexes */
const IX_DEFAULTS = { status: 'active', deposited_sol: 0, withdrawn_sol: 0, last_rebalance: null, interval_min: 120, fee_bps: 50, fees_paid_sol: 0 };
export async function getIndex(id, owner) {
  const ix = J(await kv('HGET', P + 'ix', id));
  if (!ix || (owner && ix.owner !== owner)) return null;
  return { ...IX_DEFAULTS, ...ix };
}
export async function createIndex(ix) {
  const rec = { ...IX_DEFAULTS, ...ix, created_at: now() };
  await pipe([['HSET', P + 'ix', ix.id, JSON.stringify(rec)], ['SADD', P + 'owner:' + ix.owner, ix.id]]);
  return rec;
}
// read-modify-write of one index; fn gets the record and returns the fields to change
export async function updateIndex(id, fn) {
  const ix = J(await kv('HGET', P + 'ix', id));
  if (!ix) return null;
  const next = { ...ix, ...fn({ ...IX_DEFAULTS, ...ix }) };
  await kv('HSET', P + 'ix', id, JSON.stringify(next));
  return next;
}
export async function indexesOf(owner) {
  const ids = (await kv('SMEMBERS', P + 'owner:' + owner)) || [];
  if (!ids.length) return [];
  const rows = await pipe(ids.map((id) => ['HGET', P + 'ix', id]));
  return rows.map(J).filter(Boolean).map((ix) => ({ ...IX_DEFAULTS, ...ix })).sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
}
export async function allIndexes() {
  const h = (await kv('HGETALL', P + 'ix')) || [];
  const out = [];
  for (let i = 1; i < h.length; i += 2) { const ix = J(h[i]); if (ix) out.push({ ...IX_DEFAULTS, ...ix }); }
  return out;
}
export function isDue(ix) {
  if (ix.status !== 'active') return false;
  if (!ix.last_rebalance) return true;
  return Date.now() - new Date(ix.last_rebalance).getTime() >= (Number(ix.interval_min) || 120) * 60000;
}

/* ---------------------------------------------------------------- snapshots, trades */
export async function addSnapshot(id, s) {
  const k = P + 'snap:' + id;
  await pipe([['RPUSH', k, JSON.stringify({ ts: now(), ...s })], ['LTRIM', k, -2000, -1]]);
}
export async function snapshots(id) { return ((await kv('LRANGE', P + 'snap:' + id, 0, -1)) || []).map(J).filter(Boolean); }
export async function lastSnapshot(id) { return J(await kv('LINDEX', P + 'snap:' + id, -1)); }

export async function addTrade(id, t) {
  const k = P + 'trades:' + id;
  const cmds = [['LPUSH', k, JSON.stringify({ ts: now(), ...t })], ['LTRIM', k, 0, 499]];
  if (t.sig) cmds.push(['SADD', P + 'sigs:' + id, t.sig]);
  await pipe(cmds);
}
export async function trades(id, n = 100) { return ((await kv('LRANGE', P + 'trades:' + id, 0, n - 1)) || []).map(J).filter(Boolean); }
export async function hasSig(id, sig) { return (await kv('SISMEMBER', P + 'sigs:' + id, sig)) === 1; }

/* ---------------------------------------------------------------- token cache */
export async function tokensGet(mints) {
  if (!mints.length) return new Map();
  const rows = await kv('HMGET', P + 'tok', ...mints);
  const out = new Map();
  mints.forEach((m, i) => { const r = J(rows?.[i]); if (r) out.set(m, { mint: m, ...r }); });
  return out;
}
export async function tokenSet(mint, fields) {
  const cur = J(await kv('HGET', P + 'tok', mint)) || {};
  await kv('HSET', P + 'tok', mint, JSON.stringify({ ...cur, ...fields, updated_at: fields.updated_at ?? cur.updated_at ?? null }));
}

/* ---------------------------------------------------------------- traders: the fomo directory + our overlay */
let namesMem = null;
async function allNames() {
  if (namesMem && Date.now() - namesMem.at < 600000) return namesMem.list;
  const list = ((await kv('SMEMBERS', 'fp:fomo:handles')) || []).sort();
  namesMem = { at: Date.now(), list };
  return list;
}
let popMem = null;
async function popularList() {
  if (popMem && Date.now() - popMem.at < 600000) return popMem.list;
  const list = J(await kv('GET', P + 'popular')) || [];
  popMem = { at: Date.now(), list };
  return list;
}
async function leaderboard() { return J(await kv('GET', P + 'lb')) || []; }
export async function setLeaderboard(rows) { await kv('SET', P + 'lb', JSON.stringify(rows)); }

// full records for handles: directory profile merged with our overlay
export async function traders(handles) {
  handles = [...new Set(handles.map((h) => String(h || '').replace(/^@/, '').toLowerCase()).filter(Boolean))];
  if (!handles.length) return new Map();
  const res = await pipe(handles.flatMap((h) => [['GET', 'fp:fomo:handle:' + h], ['GET', P + 'trader:' + h]]));
  const lb = new Map((await leaderboard()).map((r) => [r.handle.toLowerCase(), r]));
  const out = new Map();
  handles.forEach((h, i) => {
    const d = J(res[2 * i]) || null, o = J(res[2 * i + 1]) || {};
    if (!d && !o.handle) return;
    const l = lb.get(h) || {};
    out.set(h, {
      handle: d?.handle || o.handle || h, name: o.name || d?.name || d?.handle || h, avatar: o.avatar || d?.avatar || null,
      // fomo's `address` is not where the trader trades, so only a confirmed trading wallet counts: one found on the chain
      // from their fomo balances (tools/resolve_wallets.py, FOMOBOT) or set by hand. No confirmed wallet, no mirroring.
      wallet: o.wallet || d?.trade_wallet || null, fomo_address: d?.wallet || null, rank: o.rank ?? l.rank ?? null, pnl_7d: o.pnl_7d ?? l.pnl_7d ?? null,
      active: o.active !== false, positions: o.positions || null, positions_at: o.positions_at || null, source: d ? 'fomo' : 'manual',
      track: o.track || null,
    });
  });
  return out;
}
export async function trader(handle) { return (await traders([handle])).get(String(handle || '').replace(/^@/, '').toLowerCase()) || null; }
export async function setTraderOverlay(handle, fields) {
  const k = P + 'trader:' + String(handle).replace(/^@/, '').toLowerCase();
  const cur = J(await kv('GET', k)) || { handle };
  await kv('SET', k, JSON.stringify({ ...cur, ...fields }));
}

// browse or search the directory: leaderboard first, then traders with a picture, then everyone else
export async function searchTraders(q = '', offset = 0, limit = 60) {
  q = String(q || '').trim().replace(/^@/, '').toLowerCase();
  const names = await allNames();
  let pool;
  if (q) {
    pool = [...names.filter((n) => n.startsWith(q)), ...names.filter((n) => n.includes(q) && !n.startsWith(q))];
  } else {
    // FOMO's leaderboard first (while the fomo session works), then the most popular (lib/popular.mjs), then the rest
    const lb = (await leaderboard()).map((r) => r.handle.toLowerCase());
    const pop = await popularList();
    const seen = new Set();
    pool = [...lb, ...pop, ...names].filter((n) => !seen.has(n) && seen.add(n));
  }
  const page = pool.slice(offset, offset + limit);
  const got = await traders(page);
  const rows = page.map((h, i) => { const r = got.get(h); if (r && !q) r.pop = offset + i + 1; return r; }).filter(Boolean);
  return { total: pool.length, rows };
}
export async function staleTraders(n = 40) {
  // traders that sit in an index, oldest positions first, so the engine has fresh books for the ones that matter
  const handles = new Set();
  for (const ix of await allIndexes()) if (ix.status === 'active') for (const t of ix.traders || []) handles.add(t.handle.toLowerCase());
  const got = await traders([...handles]);
  return [...got.values()].filter((t) => t.wallet && t.active).sort((a, b) => String(a.positions_at || '').localeCompare(String(b.positions_at || ''))).slice(0, n);
}

/* ---------------------------------------------------------------- tracking, as on FOMOFANTASY
   Every time a trader's wallet is read, a point is stored: the wallet's value and the price and weight of each
   holding. The score is a chained index of what the trader holds (the weighted price move from one point to the
   next), so money going in or out of the wallet does not count as a gain or a loss.
   fi:track:<handle>  list of {t, usd, idx, px:{mint:price}, w:{mint:weight}}, oldest first (last 1500) */
const TRACK_GAP = 9 * 60000;
function summary(points) {
  if (!points.length) return null;
  const last = points[points.length - 1];
  const at = (ms) => { const want = last.t - ms; let p = null; for (const x of points) { if (x.t <= want) p = x; else break; } return p; };
  const ch = (p) => (p && p.idx ? last.idx / p.idx - 1 : null);
  return { idx: last.idx, value_usd: last.usd, since: points[0].t, points: points.length, change_24h: ch(at(86400000)), change_7d: ch(at(7 * 86400000)), change_all: points[0].idx ? last.idx / points[0].idx - 1 : null };
}
export async function trackPoint(handle, p) {
  const h = String(handle).replace(/^@/, '').toLowerCase(), k = P + 'track:' + h;
  const last = J(await kv('LINDEX', k, -1));
  const t = Date.now();
  if (last && t - last.t < TRACK_GAP) return;
  const px = {}, w = {};
  for (const r of (p.rows || []).filter((x) => x.price_usd && x.weight > 0).sort((a, b) => b.weight - a.weight).slice(0, 15)) { px[r.mint] = r.price_usd; w[r.mint] = r.weight; }
  let idx = 1;
  if (last) {
    let ret = 0;
    for (const [m, wt] of Object.entries(last.w || {})) { const a = last.px?.[m], b = px[m]; if (a && b) ret += wt * (b / a - 1); }
    idx = (last.idx || 1) * (1 + ret);
  }
  await pipe([['RPUSH', k, JSON.stringify({ t, usd: p.total_usd || 0, idx, px, w })], ['LTRIM', k, -1500, -1]]);
  const pts = ((await kv('LRANGE', k, 0, -1)) || []).map(J).filter(Boolean);
  await setTraderOverlay(h, { track: summary(pts) });
}
// a new wallet starts a new history: points read from another wallet say nothing about this one
export async function resetTrack(handle) {
  const h = String(handle).replace(/^@/, '').toLowerCase();
  await kv('DEL', P + 'track:' + h);
  await setTraderOverlay(h, { track: null });
}
export async function trackOf(handle) {
  const pts = ((await kv('LRANGE', P + 'track:' + String(handle).replace(/^@/, '').toLowerCase(), 0, -1)) || []).map(J).filter(Boolean);
  return { ...(summary(pts) || {}), history: pts.map((x) => ({ t: x.t, idx: x.idx, usd: x.usd })) };
}

// the shared FOMO session (for the leaderboard); null when there is none
export async function fomoSession() { return J(await kv('GET', 'fp:fomo:session')); }
