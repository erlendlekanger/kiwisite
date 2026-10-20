// The browser's line to Solana for "Send with wallet". Solana's public RPC answers 403 to web pages, so the page
// asks here and this forwards to our own RPC. Only the few read calls the deposit needs are let through.
import { wrap, json, body, fail } from '../lib/http.mjs';
const ALLOWED = new Set(['getLatestBlockhash', 'getSignatureStatuses', 'getBalance', 'getBlockHeight']);
export default wrap(async (req, res) => {
  if (req.method !== 'POST') throw fail(405, 'POST a JSON-RPC call');
  const b = await body(req);
  if (Array.isArray(b) || !ALLOWED.has(b?.method)) throw fail(400, 'that call is not available here');
  const r = await fetch(process.env.RPC_URL || 'https://api.mainnet-beta.solana.com', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', id: b.id ?? 1, method: b.method, params: b.params || [] }),
  });
  json(res, r.status, await r.json());
});
