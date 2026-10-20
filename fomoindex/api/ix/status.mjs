// POST /api/ix/:id/status { status: 'active' | 'paused' }
import { wrap, json, query, body, fail } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { log, getIndex, updateIndex } from '../../lib/db.mjs';
export default wrap(async (req, res) => {
  const owner = requireUser(req); const { id } = query(req); const { status } = await body(req);
  if (!['active', 'paused'].includes(status)) throw fail(400, 'status must be active or paused');
  const ix = await getIndex(id, owner);
  if (!ix || ix.status === 'closed') throw fail(404, 'no such index');
  await updateIndex(id, () => ({ status }));
  await log(id, 'info', `index ${status}`);
  json(res, 200, { ok: true, status });
});
