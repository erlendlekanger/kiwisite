// Reports which server modules load, so a broken deploy explains itself. No secrets are printed.
export default async function handler(req, res) {
  const out = { node: process.version, modules: {} };
  for (const m of ['../lib/http.mjs', '../lib/db.mjs', '../lib/auth.mjs', '../lib/solana.mjs', '../lib/index.mjs']) {
    try { await import(m); out.modules[m] = 'ok'; } catch (e) { out.modules[m] = String(e && e.stack || e).split('\n').slice(0, 4).join(' | '); }
  }
  res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(out, null, 2));
}
