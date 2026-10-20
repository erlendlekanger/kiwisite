// POST /api/ix/:id/withdraw -> sells everything to SOL and sends it to the owner's wallet.
import { wrap, json, query, fail } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { getIndex, updateIndex } from '../../lib/db.mjs';
import { liquidate } from '../../lib/index.mjs';
export default wrap(async (req, res) => {
  const owner = requireUser(req); const { id } = query(req);
  const ix = await getIndex(id, owner);
  if (!ix) throw fail(404, 'no such index');
  await updateIndex(id, () => ({ status: 'withdrawing' }));
  const r = await liquidate(ix, owner);
  json(res, 200, r);
});
