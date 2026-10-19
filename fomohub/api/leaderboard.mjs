// Vercel serverless function: proxies the fomo leaderboard so the hub can show it.
// fomo's API (prod-api.fomo.family/v2/leaderboard) needs a logged-in session, so set the
// environment variable FOMO_API_TOKEN (a bearer token) or FOMO_COOKIE (a session cookie) on the
// deployment. Without either this route answers 503 and the page falls back to a link to fomo.
const RANGES = new Set(['24h', '7d', '30d', 'all-time']);

export default async function handler(req, res) {
  const range = RANGES.has(req.query.range) ? req.query.range : '24h';
  const token = process.env.FOMO_API_TOKEN, cookie = process.env.FOMO_COOKIE;
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 's-maxage=60, stale-while-revalidate=300');
  if (!token && !cookie) return res.status(503).json({ error: 'FOMO_API_TOKEN or FOMO_COOKIE is not set' });
  const url = 'https://prod-api.fomo.family/v2/leaderboard' + (range === 'all-time' ? '' : '/' + range);
  const headers = { Accept: 'application/json' };
  if (token) headers.Authorization = 'Bearer ' + token;
  if (cookie) headers.Cookie = cookie;
  try {
    const r = await fetch(url, { headers });
    const j = await r.json();
    if (!r.ok || j.statusCode && j.statusCode !== 200) return res.status(502).json({ error: 'fomo answered ' + r.status });
    return res.status(200).json({ range, leaderboard: j.responseObject?.leaderboard || j.leaderboard || [] });
  } catch (e) {
    return res.status(502).json({ error: 'could not reach fomo' });
  }
}
