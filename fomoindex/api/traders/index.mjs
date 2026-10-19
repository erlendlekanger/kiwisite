// The traders you can put in an index: everyone we have a wallet for, with their latest on-chain positions summary.
import { wrap, json } from '../../lib/http.mjs';
import { q } from '../../lib/db.mjs';
export default wrap(async (req, res) => {
  const rows = await q(`SELECT handle, name, avatar, rank, pnl_24h, pnl_7d, pnl_30d, source, active, wallet IS NOT NULL AS has_wallet, positions, positions_at
    FROM traders ORDER BY active DESC, rank NULLS LAST, pnl_7d DESC NULLS LAST LIMIT 200`);
  json(res, 200, { traders: rows.map((r) => ({ ...r, top: (r.positions?.rows || []).filter((x) => x.mint !== 'So11111111111111111111111111111111111111112').slice(0, 4).map((x) => ({ symbol: x.symbol, icon: x.icon, weight: x.weight })), positions: undefined })) });
});
