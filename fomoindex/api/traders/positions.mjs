// A trader's live portfolio, cached for 10 minutes.
import { wrap, json, query, fail } from '../../lib/http.mjs';
import { q } from '../../lib/db.mjs';
import { portfolio } from '../../lib/solana.mjs';
export async function traderPortfolio(handle, maxAgeMin = 10) {
  const [t] = await q('SELECT handle, wallet, positions, positions_at FROM traders WHERE handle=$1', [handle]);
  if (!t) throw fail(404, 'unknown trader');
  if (!t.wallet) throw fail(409, 'this trader has no wallet on file yet');
  if (t.positions && t.positions_at && Date.now() - new Date(t.positions_at).getTime() < maxAgeMin * 60000) return t.positions;
  const p = await portfolio(t.wallet);
  await q('UPDATE traders SET positions=$2, positions_at=now() WHERE handle=$1', [handle, JSON.stringify(p)]);
  return p;
}
export default wrap(async (req, res) => {
  const { handle } = query(req);
  json(res, 200, await traderPortfolio(handle));
});
