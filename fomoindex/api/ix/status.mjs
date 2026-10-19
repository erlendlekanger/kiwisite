// POST /api/ix/:id/status { status: 'active' | 'paused' }
import { wrap, json, query, body, fail } from '../../lib/http.mjs';
import { requireUser } from '../../lib/auth.mjs';
import { q, log } from '../../lib/db.mjs';
export default wrap(async (req, res) => {
  const owner = requireUser(req); const { id } = query(req); const { status } = await body(req);
  if (!['active', 'paused'].includes(status)) throw fail(400, 'status must be active or paused');
  const r = await q('UPDATE indexes SET status=$3 WHERE id=$1 AND owner=$2 AND status<>\'closed\' RETURNING id', [id, owner, status]);
  if (!r.length) throw fail(404, 'no such index');
  await log(id, 'info', `index ${status}`);
  json(res, 200, { ok: true, status });
});
