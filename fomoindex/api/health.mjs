import { wrap, json } from '../lib/http.mjs';
import { q } from '../lib/db.mjs';
import { solPrice } from '../lib/solana.mjs';
export default wrap(async (req, res) => {
  const out = { ok: true, db: false, sol_usd: 0, env: { DATABASE_URL: !!process.env.DATABASE_URL, MASTER_KEY: (process.env.MASTER_KEY || '').length === 64, SESSION_SECRET: !!process.env.SESSION_SECRET, RPC_URL: !!process.env.RPC_URL, FOMO: !!(process.env.FOMO_API_TOKEN || process.env.FOMO_COOKIE) } };
  try { await q('SELECT 1'); out.db = true; } catch (e) { out.ok = false; out.db_error = e.message; }
  try { out.sol_usd = await solPrice(); } catch (e) { out.sol_usd = 0; }
  json(res, 200, out);
});
