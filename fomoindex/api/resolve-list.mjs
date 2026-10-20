// The traders still missing a confirmed trading wallet, most popular first, as [handle, fomo user id].
// Read by the Console helper the operator runs on fomo.family (tools/fomo_console.js): their own logged-in fomo tab asks
// fomo for these traders' balances and saves them, and tools/match_balances.py finds the wallets on the chain.
// Only usernames and fomo's public user ids, so it is open to fomo.family's page.
import { wrap, json, query } from '../lib/http.mjs';
import { kv } from '../lib/db.mjs';
const J = (s) => { try { return JSON.parse(s); } catch { return null; } };
export default wrap(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', 'https://fomo.family');
  if (req.method === 'OPTIONS') { res.statusCode = 204; return res.end(); }
  const n = Math.min(2000, Math.max(1, Number(query(req).n) || 300));
  const order = J(await kv('GET', 'fi:popular')) || [];
  const ids = [];
  for (let i = 0; i < order.length && ids.length < n; i += 500) {
    const recs = await kv('MGET', ...order.slice(i, i + 500).map((h) => 'fp:fomo:handle:' + h));
    for (const r of recs.map(J)) if (r?.id && !r.trade_wallet && ids.length < n) ids.push([r.handle, r.id]);
  }
  json(res, 200, { ids });
});
