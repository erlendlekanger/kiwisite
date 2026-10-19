import { wrap, json, body, fail } from '../../lib/http.mjs';
import { verifyLogin, sessionCookie } from '../../lib/auth.mjs';
export default wrap(async (req, res) => {
  const { wallet, nonce, signature } = await body(req);
  if (!wallet || !nonce || !signature) throw fail(400, 'wallet, nonce and signature required');
  const token = await verifyLogin(wallet, nonce, signature);
  res.setHeader('Set-Cookie', sessionCookie(token));
  json(res, 200, { ok: true, wallet, token });
});
