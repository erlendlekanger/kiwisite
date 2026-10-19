// GET /api/ix/:id -> live state: holdings, targets, history, trades, events.
import { wrap, json, query, fail } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { q } from '../../lib/db.mjs';
import { indexState } from '../../lib/index.mjs';
import { tokenInfo } from '../../lib/solana.mjs';
export default wrap(async (req, res) => {
  const owner = requireUser(req);
  const { id } = query(req);
  const [ix] = await q('SELECT * FROM indexes WHERE id=$1 AND owner=$2', [id, owner]);
  if (!ix) throw fail(404, 'no such index');
  const st = await indexState(ix);
  const info = await tokenInfo([...st.target.keys()]);
  const target = [...st.target.entries()].map(([mint, w]) => ({ mint, weight: w, symbol: info.get(mint)?.symbol, icon: info.get(mint)?.icon })).sort((a, b) => b.weight - a.weight);
  const [history, trades, events, traders] = await Promise.all([
    q('SELECT ts, nav_sol, nav_usd, sol_usd FROM snapshots WHERE index_id=$1 ORDER BY ts ASC LIMIT 2000', [id]),
    q('SELECT ts, side, mint, symbol, amount_sol, amount_token, price_usd, sig, note FROM trades WHERE index_id=$1 ORDER BY ts DESC LIMIT 100', [id]),
    q('SELECT ts, level, message FROM events WHERE index_id=$1 ORDER BY ts DESC LIMIT 50', [id]),
    q('SELECT handle, name, avatar, pnl_7d, rank FROM traders WHERE handle = ANY($1)', [ix.traders.map((t) => t.handle)]),
  ]);
  json(res, 200, {
    id: ix.id, name: ix.name, status: ix.status, deposit: ix.deposit_pubkey, created_at: ix.created_at, last_rebalance: ix.last_rebalance,
    deposited_sol: Number(ix.deposited_sol), withdrawn_sol: Number(ix.withdrawn_sol), interval_min: ix.interval_min, fee_bps: ix.fee_bps, fees_paid_sol: Number(ix.fees_paid_sol || 0),
    traders: ix.traders.map((t) => ({ ...t, ...(traders.find((x) => x.handle === t.handle) || {}) })),
    nav_sol: st.nav_sol, nav_usd: st.nav_usd, sol_usd: st.sol_usd,
    holdings: st.portfolio.rows.map((r) => ({ mint: r.mint, symbol: r.symbol, name: r.name, icon: r.icon, amount: r.amount, usd: r.usd, weight: r.weight, price_usd: r.price_usd })),
    target, history, trades, events,
  });
});
