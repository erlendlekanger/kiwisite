// Local dev server: serves the static site and runs the api/ functions like Vercel would (rewrites included).
// usage: DATABASE_URL=... node dev.mjs [port]
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL, fileURLToPath } from 'node:url';
const root = path.dirname(fileURLToPath(import.meta.url));
// local secrets (KV, session) live outside the repo in ~/fomoindex.env
try {
  const f = path.join(process.env.USERPROFILE || process.env.HOME || '', 'fomoindex.env');
  for (const l of fs.readFileSync(f, 'utf8').split(/\r?\n/)) { const m = l.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)$/); if (m && !process.env[m[1]]) process.env[m[1]] = m[2].replace(/^"|"$/g, ''); }
} catch (e) { /* no local env file */ }
const cfg = JSON.parse(fs.readFileSync(path.join(root, 'vercel.json'), 'utf8'));
const port = +(process.argv[2] || process.env.PORT || 8790);
const types = { '.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript', '.mjs': 'text/javascript', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.json': 'application/json', '.webp': 'image/webp' };
function rewrite(pathname) {
  for (const r of cfg.rewrites || []) {
    const keys = []; const re = new RegExp('^' + r.source.replace(/:(\w+)/g, (_, k) => { keys.push(k); return '([^/]+)'; }) + '$');
    const m = pathname.match(re); if (!m) continue;
    let dest = r.destination; keys.forEach((k, i) => { dest = dest.replace(':' + k, m[i + 1]); });
    return dest;
  }
  return pathname;
}
http.createServer(async (req, res) => {
  const u = new URL(req.url, 'http://x');
  let p = rewrite(u.pathname);
  const [pp, qs] = p.split('?');
  if (pp.startsWith('/api/')) {
    const f = path.join(root, pp + '.mjs'); const f2 = path.join(root, pp, 'index.mjs');
    const file = fs.existsSync(f) ? f : fs.existsSync(f2) ? f2 : null;
    if (!file) { res.statusCode = 404; return res.end('no api'); }
    req.url = pp + '?' + new URLSearchParams([...new URLSearchParams(qs || ''), ...u.searchParams]).toString();
    const mod = await import(pathToFileURL(file).href + '?t=' + Date.now());
    return mod.default(req, res);
  }
  let file = path.join(root, pp === '/' ? 'index.html' : pp);
  if (!path.extname(file) && fs.existsSync(file + '.html')) file += '.html';
  if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.statusCode = 404; return res.end('not found'); }
  res.setHeader('Content-Type', types[path.extname(file)] || 'application/octet-stream');
  res.setHeader('Cache-Control', 'no-store');   // lokalt: alltid nyeste fil, ellers viser nettleseren gammel css
  fs.createReadStream(file).pipe(res);
}).listen(port, () => console.log('dev on http://localhost:' + port));
