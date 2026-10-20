// GET: my indexes. POST: create one { name, traders:[{handle, weight}] } -> deposit address. 1 to 5 fomo traders.
import crypto from 'node:crypto';
import { wrap, json, body, fail, query } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { log, traders as tradersOf, createIndex, indexesOf, lastSnapshot } from '../../lib/db.mjs';
import { newIndexWallet, FEE_LADDER, feeBpsFor } from '../../lib/solana.mjs';
export const MAX_TRADERS = 5;
export default wrap(async (req, res) => {
  const owner = requireUser(req);
  if (req.method === 'POST') {
    const b = await body(req);
    const name = String(b.name || '').trim().slice(0, 40) || 'My index';
    let traders = Array.isArray(b.traders) ? b.traders : [];
    traders = traders.map((t) => ({ handle: String(t.handle || '').replace(/^@/, ''), weight: Number(t.weight) })).filter((t) => t.handle && t.weight > 0);
    if (traders.length < 1 || traders.length > MAX_TRADERS) throw fail(400, `pick between 1 and ${MAX_TRADERS} traders`);
    const known = await tradersOf(traders.map((t) => t.handle));
    if (traders.some((t) => !known.get(t.handle.toLowerCase())?.wallet || known.get(t.handle.toLowerCase())?.active === false)) throw fail(400, 'one of the traders is not available for mirroring yet');
    traders = traders.map((t) => ({ ...t, handle: known.get(t.handle.toLowerCase()).handle }));
    const sum = traders.reduce((s, t) => s + t.weight, 0);
    traders = traders.map((t) => ({ ...t, weight: t.weight / sum }));
    const interval = Number(b.interval_min);
    if (!FEE_LADDER.some((f) => f.minutes === interval)) throw fail(400, 'pick a rebalance interval from the ladder');
    const fee_bps = feeBpsFor(interval);
    const id = crypto.randomBytes(6).toString('base64url');
    const w = newIndexWallet();
    await createIndex({ id, owner, name, traders, deposit_pubkey: w.pubkey, secret_enc: w.secret_enc, interval_min: interval, fee_bps });
    await log(id, 'info', 'index created', { traders, interval, fee_bps });
    return json(res, 200, { id, name, traders, deposit: w.pubkey, interval_min: interval, fee_bps });
  }
  if (req.method === 'OPTIONS' || query(req).ladder) return json(res, 200, { ladder: FEE_LADDER, max_traders: MAX_TRADERS });
  const list = await indexesOf(owner);
  const snaps = await Promise.all(list.map((ix) => lastSnapshot(ix.id)));
  json(res, 200, {
    indexes: list.map((ix, i) => ({
      id: ix.id, name: ix.name, traders: ix.traders, deposit: ix.deposit_pubkey, status: ix.status, deposited_sol: ix.deposited_sol, withdrawn_sol: ix.withdrawn_sol,
      last_rebalance: ix.last_rebalance, created_at: ix.created_at, interval_min: ix.interval_min, fee_bps: ix.fee_bps, fees_paid_sol: ix.fees_paid_sol,
      nav_sol: snaps[i]?.nav_sol ?? null, nav_usd: snaps[i]?.nav_usd ?? null, nav_at: snaps[i]?.ts ?? null,
    })),
  });
});
