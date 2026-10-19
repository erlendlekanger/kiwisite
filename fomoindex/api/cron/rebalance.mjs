// Rebalance the stalest active index. Call it repeatedly (GitHub Actions every 30 min, or Vercel Cron on Pro);
// each call does one index so it fits in a function's time budget. ?all=1 processes up to 3.
import { wrap, json, query } from '../../lib/http.mjs';
import { requireKey } from '../../lib/auth.mjs';
import { q, log } from '../../lib/db.mjs';
import { rebalance } from '../../lib/index.mjs';
export default wrap(async (req, res) => {
  requireKey(req, 'CRON_SECRET');
  const n = query(req).all ? 3 : 1;
  const due = `status='active' AND (last_rebalance IS NULL OR last_rebalance < now() - (COALESCE(interval_min, 120) * interval '1 minute'))`;
  const list = await q(`SELECT * FROM indexes WHERE ${due} ORDER BY last_rebalance NULLS FIRST LIMIT $1`, [n]);
  const out = [];
  for (const ix of list) {
    try { out.push({ id: ix.id, ...(await rebalance(ix)) }); }
    catch (e) { await log(ix.id, 'error', 'rebalance failed: ' + e.message); out.push({ id: ix.id, error: e.message }); await q('UPDATE indexes SET last_rebalance=now() WHERE id=$1', [ix.id]); }
  }
  json(res, 200, { processed: out, remaining: (await q(`SELECT count(*)::int AS c FROM indexes WHERE ${due}`))[0].c });
});
