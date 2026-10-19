// Pull the fomo leaderboard (needs a fomo session) and refresh positions for every trader with a wallet.
import { wrap, json } from '../../lib/http.mjs';
import { requireKey } from '../../lib/auth.mjs';
import { q, log } from '../../lib/db.mjs';
import { traderPortfolio } from '../traders/positions.mjs';
const looksLikePubkey = (s) => typeof s === 'string' && /^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(s);
async function fomo(path) {
  const headers = { Accept: 'application/json' };
  if (process.env.FOMO_API_TOKEN) headers.Authorization = 'Bearer ' + process.env.FOMO_API_TOKEN;
  if (process.env.FOMO_COOKIE) headers.Cookie = process.env.FOMO_COOKIE;
  const r = await fetch('https://prod-api.fomo.family' + path, { headers });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(`fomo ${path} -> ${r.status}`);
  return j.responseObject ?? j;
}
export default wrap(async (req, res) => {
  requireKey(req, 'CRON_SECRET');
  const out = { leaderboard: 0, positions: 0, errors: [] };
  if (process.env.FOMO_API_TOKEN || process.env.FOMO_COOKIE) {
    for (const range of ['7d']) {
      try {
        const lb = await fomo('/v2/leaderboard/' + range);
        const list = lb.leaderboard || lb || [];
        for (const [i, u] of list.entries()) {
          const handle = (u.handle || u.username || u.name || '').replace(/^@/, ''); if (!handle) continue;
          const wallet = [u.wallet, u.walletAddress, u.address, u.publicKey, u.solanaAddress].find(looksLikePubkey) || null;
          await q(`INSERT INTO traders(handle, name, wallet, avatar, rank, pnl_7d, source, updated_at) VALUES ($1,$2,$3,$4,$5,$6,'fomo',now())
            ON CONFLICT (handle) DO UPDATE SET name=COALESCE($2, traders.name), wallet=COALESCE(traders.wallet, $3), avatar=COALESCE($4, traders.avatar), rank=$5, pnl_7d=$6, updated_at=now()`,
            [handle, u.displayName || u.name || null, wallet, u.profilePictureLink || u.avatar || null, u.rank || i + 1, Number(u.pnl ?? u.pnlUsd ?? 0)]);
          out.leaderboard++;
        }
      } catch (e) { out.errors.push(String(e.message)); }
    }
  }
  const traders = await q('SELECT handle FROM traders WHERE active AND wallet IS NOT NULL ORDER BY positions_at NULLS FIRST LIMIT 40');
  for (const t of traders) {
    try { await traderPortfolio(t.handle, 20); out.positions++; } catch (e) { out.errors.push(`${t.handle}: ${e.message}`); }
  }
  await log(null, 'info', 'sync-traders', out);
  json(res, 200, out);
});
