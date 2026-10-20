// POST /api/ix/:id/deposit { sig } -> verifies a SOL transfer into the index wallet and records it.
import { wrap, json, query, body, fail } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { log, getIndex, hasSig, addTrade, updateIndex } from '../../lib/db.mjs';
import { conn, LAMPORTS_PER_SOL } from '../../lib/solana.mjs';
export default wrap(async (req, res) => {
  const owner = requireUser(req); const { id } = query(req); const { sig } = await body(req);
  if (!sig || typeof sig !== 'string') throw fail(400, 'signature required');
  const ix = await getIndex(id, owner);
  if (!ix) throw fail(404, 'no such index');
  if (await hasSig(id, sig)) return json(res, 200, { ok: true, duplicate: true });
  let tx; try { tx = await conn().getParsedTransaction(sig, { maxSupportedTransactionVersion: 0, commitment: 'confirmed' }); } catch (e) { throw fail(400, 'that does not look like a transaction signature'); }
  if (!tx || tx.meta?.err) throw fail(400, 'transaction not found or failed');
  const keys = tx.transaction.message.accountKeys.map((k) => (k.pubkey || k).toString());
  const i = keys.indexOf(ix.deposit_pubkey);
  if (i < 0) throw fail(400, 'that transaction does not touch this index');
  const lamports = (tx.meta.postBalances[i] || 0) - (tx.meta.preBalances[i] || 0);
  if (lamports <= 0) throw fail(400, 'no SOL arrived in that transaction');
  const sol = lamports / LAMPORTS_PER_SOL;
  await addTrade(id, { side: 'deposit', mint: 'So11111111111111111111111111111111111111112', symbol: 'SOL', amount_sol: sol, sig, note: 'deposit' });
  await updateIndex(id, (x) => ({ deposited_sol: Number(x.deposited_sol || 0) + sol, last_rebalance: null }));
  await log(id, 'info', `deposit of ${sol.toFixed(4)} SOL recorded`, { sig });
  json(res, 200, { ok: true, sol });
});
