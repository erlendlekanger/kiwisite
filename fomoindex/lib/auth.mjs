// Sign-in with a Solana wallet: the wallet signs a nonce, the server verifies and issues an HMAC session.
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const nacl = require('tweetnacl');
const bs58pkg = require('bs58'); const bs58 = bs58pkg.default || bs58pkg;
import { q } from './db.mjs';
import { cookies, bearer, fail } from './http.mjs';

const SECRET = () => { if (!process.env.SESSION_SECRET) throw new Error('SESSION_SECRET is not set'); return process.env.SESSION_SECRET; };
const DAY = 86400;

export function loginMessage(nonce, wallet) {
  return `FOMOINDEX wants you to sign in.\n\nWallet: ${wallet}\nNonce: ${nonce}\n\nThis signature does not cost anything and does not move funds.`;
}

export async function makeNonce(wallet) {
  const nonce = crypto.randomBytes(16).toString('hex');
  await q('DELETE FROM nonces WHERE created_at < now() - interval \'15 minutes\'');
  await q('INSERT INTO nonces(nonce, wallet) VALUES ($1,$2)', [nonce, wallet]);
  return nonce;
}

export async function verifyLogin(wallet, nonce, signatureB58) {
  const rows = await q('DELETE FROM nonces WHERE nonce=$1 AND wallet=$2 RETURNING nonce', [nonce, wallet]);
  if (!rows.length) throw fail(400, 'nonce expired, try again');
  let pub, sig;
  try { pub = bs58.decode(wallet); sig = bs58.decode(signatureB58); } catch (e) { throw fail(400, 'bad wallet or signature encoding'); }
  const ok = nacl.sign.detached.verify(new TextEncoder().encode(loginMessage(nonce, wallet)), sig, pub);
  if (!ok) throw fail(401, 'signature does not match');
  await q('INSERT INTO users(wallet) VALUES ($1) ON CONFLICT (wallet) DO UPDATE SET last_seen=now()', [wallet]);
  return issue(wallet);
}

export function issue(wallet) {
  const exp = Math.floor(Date.now() / 1000) + 30 * DAY;
  const payload = Buffer.from(JSON.stringify({ w: wallet, exp })).toString('base64url');
  const mac = crypto.createHmac('sha256', SECRET()).update(payload).digest('base64url');
  return `${payload}.${mac}`;
}

export function readSession(token) {
  if (!token || !token.includes('.')) return null;
  const [payload, mac] = token.split('.');
  const want = crypto.createHmac('sha256', SECRET()).update(payload).digest('base64url');
  if (mac.length !== want.length || !crypto.timingSafeEqual(Buffer.from(mac), Buffer.from(want))) return null;
  try {
    const { w, exp } = JSON.parse(Buffer.from(payload, 'base64url').toString());
    if (exp < Date.now() / 1000) return null;
    return w;
  } catch (e) { return null; }
}

export function sessionCookie(token) {
  return `fi_session=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${30 * DAY}`;
}

export function requireUser(req) {
  const wallet = readSession(cookies(req).fi_session || bearer(req));
  if (!wallet) throw fail(401, 'sign in with your wallet first');
  return wallet;
}

export function requireKey(req, name) {
  const want = process.env[name];
  const got = bearer(req) || new URL(req.url, 'http://x').searchParams.get('key');
  if (!want || !got || got !== want) throw fail(401, 'not allowed');
}
