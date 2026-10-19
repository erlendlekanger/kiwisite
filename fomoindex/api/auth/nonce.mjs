import { wrap, json, body, fail } from '../../lib/http.mjs';
import { makeNonce, loginMessage } from '../../lib/auth.mjs';
export default wrap(async (req, res) => {
  const { wallet } = await body(req);
  if (!wallet || typeof wallet !== 'string' || wallet.length < 32) throw fail(400, 'wallet required');
  const nonce = await makeNonce(wallet);
  json(res, 200, { nonce, message: loginMessage(nonce, wallet) });
});
