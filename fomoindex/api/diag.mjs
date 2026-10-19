// Reports which server modules load, so a broken deploy explains itself. No secrets are printed.
const show = (e) => String((e && e.stack) || e).split('\n').slice(0, 5).join(' | ');
export default async function handler(req, res) {
  const out = { node: process.version, modules: {} };
  try { await import('../lib/http.mjs'); out.modules.http = 'ok'; } catch (e) { out.modules.http = show(e); }
  try { await import('../lib/db.mjs'); out.modules.db = 'ok'; } catch (e) { out.modules.db = show(e); }
  try { await import('../lib/auth.mjs'); out.modules.auth = 'ok'; } catch (e) { out.modules.auth = show(e); }
  try { await import('../lib/solana.mjs'); out.modules.solana = 'ok'; } catch (e) { out.modules.solana = show(e); }
  try { await import('../lib/index.mjs'); out.modules.index = 'ok'; } catch (e) { out.modules.index = show(e); }
  try { const { createRequire } = await import('node:module'); const r = createRequire(import.meta.url); r('@solana/web3.js'); out.modules.web3_cjs = 'ok'; } catch (e) { out.modules.web3_cjs = show(e); }
  try { await import('@solana/web3.js'); out.modules.web3_esm = 'ok'; } catch (e) { out.modules.web3_esm = show(e); }
  try { await import('pg'); out.modules.pg = 'ok'; } catch (e) { out.modules.pg = show(e); }
  res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(out, null, 2));
}
