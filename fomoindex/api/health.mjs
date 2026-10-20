import { wrap, json } from '../lib/http.mjs';
import { ping, kv } from '../lib/db.mjs';
import { solPrice } from '../lib/solana.mjs';
export default wrap(async (req, res) => {
  const out = { ok: true, db: false, traders: 0, sol_usd: 0, env: { KV: !!(process.env.FI_KV_REST_API_URL || process.env.KV_REST_API_URL), MASTER_KEY: (process.env.MASTER_KEY || '').length === 64, SESSION_SECRET: !!process.env.SESSION_SECRET, RPC_URL: !!process.env.RPC_URL } };
  try { out.db = await ping(); out.traders = Number(await kv('SCARD', 'fp:fomo:handles')) || 0; } catch (e) { out.ok = false; out.db_error = e.message; }
  if (!out.db) out.ok = false;
  try { out.sol_usd = await solPrice(); } catch (e) { out.sol_usd = 0; }
  json(res, 200, out);
});
