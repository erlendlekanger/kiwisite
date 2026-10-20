// A trader's live on-chain portfolio from their confirmed trading wallet, at most a minute old, plus the tracked value history.
import { wrap, json, query, fail } from '../../lib/http.mjs';
import { trader, setTraderOverlay, trackPoint, trackOf, resetTrack } from '../../lib/db.mjs';
import { portfolio } from '../../lib/solana.mjs';
export async function traderPortfolio(handle, maxAgeMin = 1) {   // a minute old at most: close to live
  const t = await trader(handle);
  if (!t) throw fail(404, 'unknown trader');
  if (!t.wallet) throw fail(409, 'we have not confirmed the wallet this trader trades from yet');
  if (t.positions && t.positions.pubkey === t.wallet && t.positions_at && Date.now() - new Date(t.positions_at).getTime() < maxAgeMin * 60000) return t.positions;
  if (t.positions && t.positions.pubkey !== t.wallet) await resetTrack(t.handle);   // the wallet changed
  const p = await portfolio(t.wallet);
  await setTraderOverlay(t.handle, { positions: p, positions_at: new Date().toISOString() });
  await trackPoint(t.handle, p);
  return p;
}
export default wrap(async (req, res) => {
  const { handle } = query(req);
  const p = await traderPortfolio(handle);
  json(res, 200, { ...p, track: await trackOf(handle) });
});
