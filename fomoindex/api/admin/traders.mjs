// Admin: add or update traders by hand (handle + wallet), e.g. from the fomofantasy list. Authorization: Bearer ADMIN_KEY.
// POST { traders: [{ handle, wallet, name?, avatar?, rank?, pnl_7d? }] }  or  { csv: "handle,wallet\nchang,4k3D..." }
import { wrap, json, body, fail } from '../../lib/http.mjs';
import { requireKey } from '../../lib/auth.mjs';
import { q } from '../../lib/db.mjs';
import { PublicKey } from '../../lib/solana.mjs';
export default wrap(async (req, res) => {
  requireKey(req, 'ADMIN_KEY');
  if (req.method === 'DELETE') { const { handle } = await body(req); await q('UPDATE traders SET active=false WHERE handle=$1', [handle]); return json(res, 200, { ok: true }); }
  const b = await body(req);
  let list = b.traders || [];
  if (b.csv) list = b.csv.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith('#') && !l.startsWith('handle')).map((l) => { const [handle, wallet, name] = l.split(',').map((s) => s.trim()); return { handle, wallet, name }; });
  const done = [];
  for (const t of list) {
    if (!t.handle) continue;
    if (t.wallet) { try { new PublicKey(t.wallet); } catch (e) { throw fail(400, `bad wallet for ${t.handle}`); } }
    await q(`INSERT INTO traders(handle, name, wallet, avatar, rank, pnl_7d, source, active, updated_at) VALUES ($1,$2,$3,$4,$5,$6,'manual',true,now())
      ON CONFLICT (handle) DO UPDATE SET wallet=COALESCE($3, traders.wallet), name=COALESCE($2, traders.name), avatar=COALESCE($4, traders.avatar), rank=COALESCE($5, traders.rank), pnl_7d=COALESCE($6, traders.pnl_7d), active=true, updated_at=now()`,
      [t.handle.replace(/^@/, ''), t.name || null, t.wallet || null, t.avatar || null, t.rank ?? null, t.pnl_7d ?? null]);
    done.push(t.handle);
  }
  json(res, 200, { ok: true, upserted: done });
});
