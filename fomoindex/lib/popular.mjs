// Who goes on top of the trader list when nobody is searching. FOMO's own leaderboard needs the shared fomo
// session; this order needs nothing but what is public or ours:
//   1. how many FOMOFANTASY teams picked the trader (real players choosing them)
//   2. the SOL in the trader's confirmed trading wallet, read on-chain 100 wallets per call
// Traders without a confirmed trading wallet come after the ones that can be mirrored. Stored as fi:popular (handles, lower case, best first).
import { kv } from './db.mjs';

const RPC = () => process.env.RPC_URL || 'https://api.mainnet-beta.solana.com';
const J = (s) => { try { return JSON.parse(s); } catch { return null; } };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function solBalances(wallets) {
  const out = new Map();
  for (let i = 0; i < wallets.length; i += 100) {
    const batch = wallets.slice(i, i + 100);
    for (let tries = 0; tries < 4; tries++) {
      try {
        const r = await fetch(RPC(), { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ jsonrpc: '2.0', id: 1, method: 'getMultipleAccounts', params: [batch, { encoding: 'base64', dataSlice: { offset: 0, length: 0 } }] }) });
        if (r.status === 429) { await sleep(1500 * (tries + 1)); continue; }
        const j = await r.json();
        (j.result?.value || []).forEach((a, k) => out.set(batch[k], a ? a.lamports / 1e9 : 0));
        break;
      } catch (e) { await sleep(800); }
    }
  }
  return out;
}

export async function rankPopular() {
  const handles = (await kv('SMEMBERS', 'fp:fomo:handles')) || [];
  const recs = [];
  for (let i = 0; i < handles.length; i += 500) {
    const v = await kv('MGET', ...handles.slice(i, i + 500).map((h) => 'fp:fomo:handle:' + h));
    v.forEach((x, k) => { const r = J(x); recs.push({ h: handles[i + k], wallet: r?.trade_wallet || null }); });   // the confirmed trading wallet; fomo's address is not it
  }
  const picks = new Map();
  const teams = (await kv('SMEMBERS', 'ff:teams')) || [];
  for (let i = 0; i < teams.length; i += 200) {
    const v = await kv('MGET', ...teams.slice(i, i + 200).map((w) => 'ff:team:' + w));
    for (const x of v) for (const s of J(x)?.slots || []) if (s?.handle) { const h = s.handle.toLowerCase(); picks.set(h, (picks.get(h) || 0) + 1); }
  }
  const sol = await solBalances([...new Set(recs.map((r) => r.wallet).filter(Boolean))]);
  const score = (r) => (r.wallet ? 1e12 : 0) + (picks.get(r.h) || 0) * 1e8 + (sol.get(r.wallet) || 0);
  const order = recs.sort((a, b) => score(b) - score(a)).map((r) => r.h);
  await kv('SET', 'fi:popular', JSON.stringify(order));
  await kv('SET', 'fi:popular_at', String(Date.now()));
  return { traders: order.length, picked: picks.size, wallets_read: sol.size, top: order.slice(0, 10) };
}
export async function popularAge() { return Date.now() - (Number(await kv('GET', 'fi:popular_at')) || 0); }
