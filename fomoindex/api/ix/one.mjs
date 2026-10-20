// GET /api/ix/:id -> live state: holdings, targets, history, trades, events, and each trader's tracked score.
import { wrap, json, query, fail } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { getIndex, snapshots, trades as tradesOf, events as eventsOf, traders as tradersOf } from '../../lib/db.mjs';
import { indexState } from '../../lib/index.mjs';
import { tokenInfo } from '../../lib/solana.mjs';
export default wrap(async (req, res) => {
  const owner = requireUser(req);
  const { id } = query(req);
  const ix = await getIndex(id, owner);
  if (!ix) throw fail(404, 'no such index');
  const st = await indexState(ix);
  const info = await tokenInfo([...st.target.keys()]);
  const target = [...st.target.entries()].map(([mint, w]) => ({ mint, weight: w, symbol: info.get(mint)?.symbol, icon: info.get(mint)?.icon })).sort((a, b) => b.weight - a.weight);
  const [history, trades, events, tmap] = await Promise.all([snapshots(id), tradesOf(id, 100), eventsOf(id, 50), tradersOf(ix.traders.map((t) => t.handle))]);
  json(res, 200, {
    id: ix.id, name: ix.name, status: ix.status, deposit: ix.deposit_pubkey, created_at: ix.created_at, last_rebalance: ix.last_rebalance,
    deposited_sol: Number(ix.deposited_sol), withdrawn_sol: Number(ix.withdrawn_sol), interval_min: ix.interval_min, fee_bps: ix.fee_bps, fees_paid_sol: Number(ix.fees_paid_sol || 0),
    traders: ix.traders.map((t) => { const x = tmap.get(t.handle.toLowerCase()) || {}; return { ...t, name: x.name, avatar: x.avatar, pnl_7d: x.pnl_7d, rank: x.rank, track: x.track || null }; }),
    nav_sol: st.nav_sol, nav_usd: st.nav_usd, sol_usd: st.sol_usd,
    holdings: st.portfolio.rows.map((r) => ({ mint: r.mint, symbol: r.symbol, name: r.name, icon: r.icon, amount: r.amount, usd: r.usd, weight: r.weight, price_usd: r.price_usd })),
    target, history: history.map((s) => ({ ts: s.ts, nav_sol: s.nav_sol, nav_usd: s.nav_usd, sol_usd: s.sol_usd })), trades, events,
  });
});
