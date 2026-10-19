import { wrap, json, cookies, bearer } from '../../lib/http.mjs';
import { readSession } from '../../lib/auth.mjs';
export default wrap(async (req, res) => {
  if (req.method === 'DELETE') { res.setHeader('Set-Cookie', 'fi_session=; Path=/; Max-Age=0'); return json(res, 200, { ok: true }); }
  json(res, 200, { wallet: readSession(cookies(req).fi_session || bearer(req)) });
});
