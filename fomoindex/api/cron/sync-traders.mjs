// Read FOMO's 7-day leaderboard with the shared fomo session (fp:fomo:session, kept fresh by FOMOPAD/FOMOFANTASY)
// and refresh the on-chain books of the traders that matter: everyone inside an active index first, then the
// leaderboard, so their tracked value history keeps growing.
import { wrap, json } from '../../lib/http.mjs';
import { requireKey } from '../../lib/auth.mjs';
import { log, fomoSession, setLeaderboard, staleTraders, traders } from '../../lib/db.mjs';
import { traderPortfolio } from '../traders/positions.mjs';
import { rankPopular, popularAge } from '../../lib/popular.mjs';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36';
async function fomo(path) {
  const s = await fomoSession();
  if (!s?.access_token) throw new Error('no fomo session');
  const r = await fetch('https://prod-api.fomo.family' + path, { headers: { Authorization: 'Bearer ' + s.access_token, Accept: 'application/json', 'User-Agent': UA, Origin: 'https://fomo.family', Referer: 'https://fomo.family/' } });
  if (!r.ok) throw new Error(`fomo ${path} -> ${r.status}`);
  const j = await r.json();
  return j.responseObject ?? j;
}
export default wrap(async (req, res) => {
  requireKey(req, 'CRON_SECRET');
  const out = { leaderboard: 0, positions: 0, errors: [] };
  let lbHandles = [];
  try {
    const body = await fomo('/v2/leaderboard/7d');
    const list = Array.isArray(body) ? body : (body.leaderboard || body.users || body.topTraders || []);
    const rows = list.map((u, i) => ({ handle: String(u.userHandle || u.handle || u.username || '').replace(/^@/, ''), rank: Number(u.rank) || i + 1, pnl_7d: Number(u.pnl ?? u.pnlUsd ?? u.profit ?? u.realizedPnl ?? 0) || null })).filter((r) => r.handle);
    if (rows.length) { await setLeaderboard(rows); out.leaderboard = rows.length; lbHandles = rows.map((r) => r.handle); }
  } catch (e) { out.errors.push(String(e.message)); }
  // the browse order (most popular first), redone every 6 hours; it takes ~16 s, so fewer wallets that run
  let budget = 45;
  if (await popularAge() > 6 * 3600e3) { try { out.popular = (await rankPopular()).traders; budget = 20; } catch (e) { out.errors.push('popular: ' + e.message); } }
  const inIndexes = await staleTraders(40);
  const extra = [...(await traders(lbHandles.slice(0, 30))).values()].filter((t) => t.wallet && !inIndexes.some((x) => x.handle === t.handle));
  for (const t of [...inIndexes, ...extra].slice(0, budget)) {
    try { await traderPortfolio(t.handle, 20); out.positions++; } catch (e) { out.errors.push(`${t.handle}: ${e.message}`); }
  }
  await log(null, 'info', 'sync-traders', out);
  json(res, 200, out);
});
