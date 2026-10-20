// Every fomo trader you can put in an index: the whole fomo directory (about 6 000 usernames with a wallet),
// FOMO's 7-day leaderboard first. ?q= searches by username, ?offset= / ?limit= page through the rest.
import { wrap, json, query } from '../../lib/http.mjs';
import { searchTraders } from '../../lib/db.mjs';
const SOL = 'So11111111111111111111111111111111111111112';
// holdings and tracking read from an older, wrong wallet (fomo's address) are not shown
const onlyConfirmed = (r) => (r.positions && r.positions.pubkey !== r.wallet ? { ...r, positions: null, positions_at: null, track: null } : r);
export default wrap(async (req, res) => {
  const { q = '', offset = '0', limit = '60' } = query(req);
  const { total, rows } = await searchTraders(q, Math.max(0, Number(offset) || 0), Math.min(200, Math.max(1, Number(limit) || 60)));
  json(res, 200, {
    total,
    traders: rows.map(onlyConfirmed).map((r) => ({
      handle: r.handle, name: r.name, avatar: r.avatar, rank: r.rank, pop: r.pop ?? null, pnl_7d: r.pnl_7d, active: r.active,
      has_wallet: !!r.wallet, wallet: r.wallet, positions_at: r.positions_at, value_usd: r.positions?.total_usd ?? null,
      change_24h: r.track?.change_24h ?? null, change_7d: r.track?.change_7d ?? null,
      top: (r.positions?.rows || []).filter((x) => x.mint !== SOL && x.weight >= 0.005).slice(0, 4).map((x) => ({ symbol: x.symbol, icon: x.icon, weight: x.weight })),
    })),
  });
});
