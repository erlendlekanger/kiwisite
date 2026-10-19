// What an index holds, what it should hold, and the rebalance that closes the gap.
import { q, log } from './db.mjs';
import { SOL, STABLES, RULES, portfolio, targetWeights, openIndexWallet, quote, swap, decimalsOf, toRaw, solPrice, sendSol, LAMPORTS_PER_SOL } from './solana.mjs';
import { traderPortfolio } from '../api/traders/positions.mjs';

const KEEP_SOL = 0.01;       // never swap away the last bit, it pays fees and rent
const MIN_TRADE_USD = 2;     // tiny orders cost more in fees than they fix

// The platform fee: a share of every trade's value, in SOL, sent to FEE_WALLET. Skipped when no wallet is set.
async function chargeFee(ix, kp, tradeSol) {
  const bps = Number(ix.fee_bps || 0); const to = process.env.FEE_WALLET;
  const feeSol = tradeSol * bps / 10000;
  if (!bps || !to || feeSol < 0.00005) return 0;
  try {
    const sig = await sendSol(kp, to, Math.floor(feeSol * LAMPORTS_PER_SOL));
    await q('UPDATE indexes SET fees_paid_sol = fees_paid_sol + $2 WHERE id=$1', [ix.id, feeSol]);
    await q('INSERT INTO trades(index_id, side, mint, symbol, amount_sol, sig, note) VALUES ($1,$2,$3,$4,$5,$6,$7)', [ix.id, 'fee', SOL, 'SOL', feeSol, sig, `${bps / 100}% fee`]);
    return feeSol;
  } catch (err) { await log(ix.id, 'warn', 'fee transfer failed: ' + err.message); return 0; }
}

export async function indexState(ix) {
  const p = await portfolio(ix.deposit_pubkey);
  const ports = [], weights = [];
  for (const t of ix.traders) {
    try { ports.push(await traderPortfolio(t.handle)); weights.push(t.weight); } catch (e) { /* trader without wallet: skipped, weight renormalised below */ }
  }
  const wsum = weights.reduce((s, w) => s + w, 0) || 1;
  const target = targetWeights(ports, weights.map((w) => w / wsum));
  const nav_sol = p.sol_usd ? p.total_usd / p.sol_usd : 0;
  return { portfolio: p, target, nav_sol, nav_usd: p.total_usd, sol_usd: p.sol_usd, tradersSeen: ports.length };
}

export async function rebalance(ix) {
  const rules = RULES();
  const st = await indexState(ix);
  const { portfolio: p, target } = st;
  const kp = openIndexWallet(ix.secret_enc);
  const total = p.total_usd;
  const done = [];
  if (total < MIN_TRADE_USD) { await snapshot(ix.id, st); await q('UPDATE indexes SET last_rebalance=now() WHERE id=$1', [ix.id]); return { skipped: 'empty', nav_usd: 0 }; }
  const cur = new Map(p.rows.map((r) => [r.mint, r]));
  const solRow = cur.get(SOL) || { amount: 0, usd: 0, price_usd: st.sol_usd };
  const solUsd = st.sol_usd || (await solPrice());
  // 1. sells: tokens we hold above target (or not in target at all)
  for (const r of p.rows) {
    if (r.mint === SOL || STABLES.has(r.mint)) continue;
    const want = (target.get(r.mint) || 0) * total;
    const diffUsd = r.usd - want;
    if (diffUsd / total * 100 < rules.threshold || diffUsd < MIN_TRADE_USD) continue;
    const frac = want === 0 ? 1 : diffUsd / r.usd;
    const amountUi = r.amount * Math.min(1, frac);
    try {
      const dec = await decimalsOf(r.mint);
      const qt = await quote(r.mint, SOL, toRaw(amountUi, dec), rules.slippageBps);
      const sig = await swap(kp, qt);
      const outSol = Number(qt.outAmount) / LAMPORTS_PER_SOL;
      await q('INSERT INTO trades(index_id, side, mint, symbol, amount_sol, amount_token, price_usd, sig) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)', [ix.id, 'sell', r.mint, r.symbol, outSol, amountUi, r.price_usd, sig]);
      await chargeFee(ix, kp, outSol);
      done.push({ side: 'sell', symbol: r.symbol, usd: diffUsd, sig });
    } catch (e) { await log(ix.id, 'warn', `sell ${r.symbol} failed: ${e.message}`); }
  }
  // 2. buys: tokens below target, paid from SOL
  let solLeft = (await portfolio(ix.deposit_pubkey)).rows.find((r) => r.mint === SOL)?.amount ?? solRow.amount;
  const buys = [...target.entries()].map(([mint, w]) => ({ mint, want: w * total, have: cur.get(mint)?.usd || 0 })).map((b) => ({ ...b, diff: b.want - b.have }))
    .filter((b) => b.diff / total * 100 >= rules.threshold && b.diff >= MIN_TRADE_USD).sort((a, b) => b.diff - a.diff);
  const feeRate = Number(ix.fee_bps || 0) / 10000;
  for (const b of buys) {
    const spendSol = Math.min(b.diff / solUsd, Math.max(0, (solLeft - KEEP_SOL) / (1 + feeRate)));
    if (spendSol * solUsd < MIN_TRADE_USD) continue;
    try {
      const qt = await quote(SOL, b.mint, toRaw(spendSol, 9), rules.slippageBps);
      const sig = await swap(kp, qt);
      const dec = await decimalsOf(b.mint);
      const gotUi = Number(qt.outAmount) / 10 ** dec;
      const sym = cur.get(b.mint)?.symbol || (await (await import('./solana.mjs')).tokenInfo([b.mint])).get(b.mint)?.symbol;
      await q('INSERT INTO trades(index_id, side, mint, symbol, amount_sol, amount_token, price_usd, sig) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)', [ix.id, 'buy', b.mint, sym, spendSol, gotUi, gotUi ? (spendSol * solUsd) / gotUi : null, sig]);
      done.push({ side: 'buy', symbol: sym, usd: spendSol * solUsd, sig });
      solLeft -= spendSol + (await chargeFee(ix, kp, spendSol));
    } catch (e) { await log(ix.id, 'warn', `buy ${b.mint.slice(0, 6)} failed: ${e.message}`); }
  }
  const after = await indexState(ix);
  await snapshot(ix.id, after);
  await q('UPDATE indexes SET last_rebalance=now() WHERE id=$1', [ix.id]);
  if (done.length) await log(ix.id, 'info', `rebalanced: ${done.length} trades`, done);
  return { trades: done, nav_usd: after.nav_usd, nav_sol: after.nav_sol };
}

export async function snapshot(id, st) {
  await q('INSERT INTO snapshots(index_id, nav_sol, nav_usd, sol_usd, holdings) VALUES ($1,$2,$3,$4,$5)',
    [id, st.nav_sol, st.nav_usd, st.sol_usd, JSON.stringify(st.portfolio.rows.map((r) => ({ mint: r.mint, symbol: r.symbol, icon: r.icon, amount: r.amount, usd: r.usd, weight: r.weight })))]);
}

export async function liquidate(ix, toWallet) {
  // sell everything to SOL, then send all SOL (minus rent) to the owner
  const kp = openIndexWallet(ix.secret_enc);
  const rules = RULES();
  const p = await portfolio(ix.deposit_pubkey);
  const sold = [];
  for (const r of p.rows) {
    if (r.mint === SOL || r.amount <= 0) continue;
    try {
      const dec = await decimalsOf(r.mint);
      const qt = await quote(r.mint, SOL, toRaw(r.amount, dec), Math.max(rules.slippageBps, 300));
      const sig = await swap(kp, qt);
      await q('INSERT INTO trades(index_id, side, mint, symbol, amount_sol, amount_token, price_usd, sig, note) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)', [ix.id, 'sell', r.mint, r.symbol, Number(qt.outAmount) / LAMPORTS_PER_SOL, r.amount, r.price_usd, sig, 'withdraw']);
      sold.push(r.symbol);
    } catch (e) { await log(ix.id, 'warn', `withdraw: could not sell ${r.symbol}: ${e.message}`); }
  }
  const { sendSol, solBalance } = await import('./solana.mjs');
  const bal = await solBalance(ix.deposit_pubkey);
  const lamports = Math.floor((bal - 0.002) * LAMPORTS_PER_SOL);
  let sig = null;
  if (lamports > 0) {
    sig = await sendSol(kp, toWallet, lamports);
    await q('UPDATE indexes SET withdrawn_sol = withdrawn_sol + $2, status=$3 WHERE id=$1', [ix.id, lamports / LAMPORTS_PER_SOL, 'closed']);
    await log(ix.id, 'info', `withdrew ${(lamports / LAMPORTS_PER_SOL).toFixed(4)} SOL to ${toWallet}`, { sig, sold });
  }
  return { sold, sol: lamports / LAMPORTS_PER_SOL, sig };
}
