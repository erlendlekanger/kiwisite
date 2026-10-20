// Admin: add or correct traders by hand (handle + wallet) on top of the fomo directory. Authorization: Bearer ADMIN_KEY.
// POST { traders: [{ handle, wallet, name?, avatar?, rank?, pnl_7d? }] }  or  { csv: "handle,wallet\nchang,4k3D..." }
// DELETE { handle } hides a trader from new indexes.
import { wrap, json, body, fail } from '../../lib/http.mjs';
import { requireKey } from '../../lib/auth.mjs';
import { setTraderOverlay } from '../../lib/db.mjs';
import { PublicKey } from '../../lib/solana.mjs';
export default wrap(async (req, res) => {
  requireKey(req, 'ADMIN_KEY');
  if (req.method === 'DELETE') { const { handle } = await body(req); await setTraderOverlay(handle, { active: false }); return json(res, 200, { ok: true }); }
  const b = await body(req);
  let list = b.traders || [];
  if (b.csv) list = b.csv.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith('#') && !l.startsWith('handle')).map((l) => { const [handle, wallet, name] = l.split(',').map((s) => s.trim()); return { handle, wallet, name }; });
  const done = [];
  for (const t of list) {
    if (!t.handle) continue;
    if (t.wallet) { try { new PublicKey(t.wallet); } catch (e) { throw fail(400, `bad wallet for ${t.handle}`); } }
    const f = { handle: t.handle.replace(/^@/, ''), active: true };
    for (const k of ['wallet', 'name', 'avatar', 'rank', 'pnl_7d']) if (t[k] != null && t[k] !== '') f[k] = t[k];
    await setTraderOverlay(f.handle, f);
    done.push(f.handle);
  }
  json(res, 200, { ok: true, upserted: done });
});
