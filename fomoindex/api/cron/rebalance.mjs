// Rebalance the stalest active index. Call it repeatedly (GitHub Actions every 30 min, or Vercel Cron on Pro);
// each call does one index so it fits in a function's time budget. ?all=1 processes up to 3.
import { wrap, json, query } from '../../lib/http.mjs';
import { requireKey } from '../../lib/auth.mjs';
import { log, allIndexes, isDue, updateIndex } from '../../lib/db.mjs';
import { rebalance } from '../../lib/index.mjs';
export default wrap(async (req, res) => {
  requireKey(req, 'CRON_SECRET');
  const n = query(req).all ? 3 : 1;
  const due = (await allIndexes()).filter(isDue).sort((a, b) => String(a.last_rebalance || '').localeCompare(String(b.last_rebalance || '')));
  const out = [];
  for (const ix of due.slice(0, n)) {
    try { out.push({ id: ix.id, ...(await rebalance(ix)) }); }
    catch (e) { await log(ix.id, 'error', 'rebalance failed: ' + e.message); out.push({ id: ix.id, error: e.message }); await updateIndex(ix.id, () => ({ last_rebalance: new Date().toISOString() })); }
  }
  json(res, 200, { processed: out, remaining: Math.max(0, due.length - out.length) });
});
