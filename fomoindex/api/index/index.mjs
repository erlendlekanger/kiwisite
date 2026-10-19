// GET: my indexes. POST: create one { name, traders:[{handle, weight}] } -> deposit address.
import crypto from 'node:crypto';
import { wrap, json, body, fail } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { q, log } from '../../lib/db.mjs';
import { newIndexWallet } from '../../lib/solana.mjs';
export default wrap(async (req, res) => {
  const owner = requireUser(req);
  if (req.method === 'POST') {
    const b = await body(req);
    const name = String(b.name || '').trim().slice(0, 40) || 'My index';
    let traders = Array.isArray(b.traders) ? b.traders : [];
    traders = traders.map((t) => ({ handle: String(t.handle || '').replace(/^@/, ''), weight: Number(t.weight) })).filter((t) => t.handle && t.weight > 0);
    if (traders.length < 1 || traders.length > 10) throw fail(400, 'pick between 1 and 10 traders');
    const known = await q('SELECT handle FROM traders WHERE active AND wallet IS NOT NULL AND handle = ANY($1)', [traders.map((t) => t.handle)]);
    if (known.length !== traders.length) throw fail(400, 'one of the traders is not available for mirroring yet');
    const sum = traders.reduce((s, t) => s + t.weight, 0);
    traders = traders.map((t) => ({ ...t, weight: t.weight / sum }));
    const id = crypto.randomBytes(6).toString('base64url');
    const w = newIndexWallet();
    await q('INSERT INTO indexes(id, owner, name, traders, deposit_pubkey, secret_enc) VALUES ($1,$2,$3,$4,$5,$6)', [id, owner, name, JSON.stringify(traders), w.pubkey, w.secret_enc]);
    await log(id, 'info', 'index created', { traders });
    return json(res, 200, { id, name, traders, deposit: w.pubkey });
  }
  const rows = await q(`SELECT i.id, i.name, i.traders, i.deposit_pubkey AS deposit, i.status, i.deposited_sol, i.withdrawn_sol, i.last_rebalance, i.created_at,
      s.nav_sol, s.nav_usd, s.ts AS nav_at
    FROM indexes i LEFT JOIN LATERAL (SELECT nav_sol, nav_usd, ts FROM snapshots WHERE index_id=i.id ORDER BY ts DESC LIMIT 1) s ON true
    WHERE i.owner=$1 ORDER BY i.created_at DESC`, [owner]);
  json(res, 200, { indexes: rows });
});
