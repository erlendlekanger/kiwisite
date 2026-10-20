// Everything on-chain: balances, prices, token metadata, Jupiter swaps, and the encrypted index wallets.
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { tokensGet, tokenSet } from './db.mjs';
// The CJS builds bundle their own dependencies, which keeps the serverless bundle self-contained.
const require = createRequire(import.meta.url);
const { Connection, Keypair, PublicKey, LAMPORTS_PER_SOL, SystemProgram, Transaction, VersionedTransaction, sendAndConfirmTransaction } = require('@solana/web3.js');
const bs58pkg = require('bs58'); const bs58 = bs58pkg.default || bs58pkg;

export const SOL = 'So11111111111111111111111111111111111111112';
export const USDC = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v';
export const USDT = 'Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCdPvTyBgM6';
export const STABLES = new Set([USDC, USDT]);
const TOKEN_PROGRAM = 'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA';
const TOKEN_2022 = 'TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb';
const JUP = 'https://lite-api.jup.ag';

export const conn = () => new Connection(process.env.RPC_URL || 'https://api.mainnet-beta.solana.com', 'confirmed');
const num = (v, d = 0) => { const n = Number(v); return Number.isFinite(n) ? n : d; };
const env = (k, d) => (process.env[k] !== undefined && process.env[k] !== '' ? Number(process.env[k]) : d);
// Rebalance interval -> fee per trade (bps of the traded value). Faster mirroring costs more.
export const FEE_LADDER = [
  { minutes: 1, bps: 100 }, { minutes: 5, bps: 80 }, { minutes: 15, bps: 60 }, { minutes: 30, bps: 50 },
  { minutes: 60, bps: 40 }, { minutes: 120, bps: 30 }, { minutes: 360, bps: 25 }, { minutes: 1440, bps: 20 },
];
export const feeBpsFor = (minutes) => (FEE_LADDER.find((f) => f.minutes === Number(minutes)) || FEE_LADDER[5]).bps;
export const RULES = () => ({
  minLiquidity: env('MIN_LIQUIDITY_USD', 50000), minWeight: env('MIN_WEIGHT_PCT', 2), threshold: env('REBALANCE_THRESHOLD_PCT', 2.5),
  slippageBps: env('MAX_SLIPPAGE_BPS', 150), maxTokens: env('MAX_TOKENS_PER_INDEX', 12),
});

/* ---------- key custody: AES-256-GCM with MASTER_KEY ---------- */
function masterKey() {
  const hex = process.env.MASTER_KEY || '';
  if (hex.length !== 64) throw new Error('MASTER_KEY must be 32 bytes as hex');
  return Buffer.from(hex, 'hex');
}
export function newIndexWallet() {
  const kp = Keypair.generate();
  const iv = crypto.randomBytes(12);
  const c = crypto.createCipheriv('aes-256-gcm', masterKey(), iv);
  const enc = Buffer.concat([c.update(Buffer.from(kp.secretKey)), c.final()]);
  return { pubkey: kp.publicKey.toBase58(), secret_enc: [iv, c.getAuthTag(), enc].map((b) => b.toString('base64')).join('.') };
}
export function openIndexWallet(secret_enc) {
  const [iv, tag, enc] = secret_enc.split('.').map((s) => Buffer.from(s, 'base64'));
  const d = crypto.createDecipheriv('aes-256-gcm', masterKey(), iv); d.setAuthTag(tag);
  return Keypair.fromSecretKey(new Uint8Array(Buffer.concat([d.update(enc), d.final()])));
}

/* ---------- balances ---------- */
export async function solBalance(pubkey) {
  return (await conn().getBalance(new PublicKey(pubkey))) / LAMPORTS_PER_SOL;
}
export async function tokenBalances(pubkey) {
  const c = conn(); const owner = new PublicKey(pubkey); const out = new Map();
  for (const programId of [TOKEN_PROGRAM, TOKEN_2022]) {
    const r = await c.getParsedTokenAccountsByOwner(owner, { programId: new PublicKey(programId) });
    for (const { account } of r.value) {
      const info = account.data.parsed.info;
      const ui = num(info.tokenAmount.uiAmount);
      if (ui > 0) out.set(info.mint, (out.get(info.mint) || 0) + ui);
    }
  }
  return out; // mint -> ui amount
}

/* ---------- prices and token info (Jupiter + DexScreener), cached ---------- */
export async function tokenInfo(mints) {
  mints = [...new Set(mints)].filter(Boolean);
  const out = new Map();
  if (!mints.length) return out;
  const cached = await tokensGet(mints);
  for (const [m, r] of cached) if (r.updated_at && Date.now() - new Date(r.updated_at).getTime() < 600000) out.set(m, r);
  const missing = mints.filter((m) => !out.has(m));
  for (let i = 0; i < missing.length; i += 30) {
    const batch = missing.slice(i, i + 30);
    try {
      const r = await fetch(`https://api.dexscreener.com/tokens/v1/solana/${batch.join(',')}`);
      const pairs = r.ok ? await r.json() : [];
      const best = new Map();
      for (const p of pairs) {
        const m = p.baseToken?.address; if (!m) continue;
        if (!best.has(m) || num(p.liquidity?.usd) > num(best.get(m).liquidity?.usd)) best.set(m, p);
      }
      for (const m of batch) {
        const p = best.get(m);
        const row = { mint: m, symbol: p?.baseToken?.symbol || m.slice(0, 4), name: p?.baseToken?.name || '', icon: p?.info?.imageUrl || null,
          decimals: null, liquidity_usd: num(p?.liquidity?.usd), price_usd: num(p?.priceUsd), mcap_usd: num(p?.marketCap || p?.fdv) };
        if (m === SOL) { row.symbol = 'SOL'; row.name = 'Solana'; row.liquidity_usd = 1e12; }
        if (STABLES.has(m)) { row.liquidity_usd = 1e12; row.price_usd = 1; }
        out.set(m, row);
        await tokenSet(m, { symbol: row.symbol, name: row.name, icon: row.icon, liquidity_usd: row.liquidity_usd, price_usd: row.price_usd, mcap_usd: row.mcap_usd, updated_at: new Date().toISOString() });
      }
    } catch (e) { for (const m of batch) if (!out.has(m)) out.set(m, { mint: m, symbol: m.slice(0, 4), price_usd: 0, liquidity_usd: 0 }); }
  }
  // SOL price straight from Jupiter, it is the unit everything is measured in
  if (out.has(SOL) && !(num(out.get(SOL).price_usd) > 0)) out.get(SOL).price_usd = await solPrice();
  return out;
}
export async function solPrice() {
  try { const r = await fetch(`${JUP}/price/v3?ids=${SOL}`); const j = await r.json(); const p = num(j[SOL]?.usdPrice); if (p > 0) return p; } catch (e) { /* fall through */ }
  try { const r = await fetch('https://api.coinbase.com/v2/prices/SOL-USD/spot'); const j = await r.json(); return num(j.data.amount); } catch (e) { return 0; }
}

/* ---------- a wallet's portfolio as weights ---------- */
export async function portfolio(pubkey) {
  const [sol, toks] = await Promise.all([solBalance(pubkey), tokenBalances(pubkey)]);
  const mints = [SOL, ...toks.keys()];
  const info = await tokenInfo(mints);
  const rows = [{ mint: SOL, amount: sol, ...pick(info.get(SOL)) }];
  for (const [mint, amount] of toks) rows.push({ mint, amount, ...pick(info.get(mint)) });
  // a token with no real market has no real value: price it at zero so junk cannot dominate the weights
  for (const r of rows) r.usd = num(r.liquidity_usd) >= 1000 ? r.amount * num(r.price_usd) : 0;
  const total = rows.reduce((s, r) => s + r.usd, 0);
  for (const r of rows) r.weight = total ? r.usd / total : 0;
  rows.sort((a, b) => b.usd - a.usd);
  return { pubkey, total_usd: total, sol_usd: num(info.get(SOL)?.price_usd), rows };
}
const pick = (i) => ({ symbol: i?.symbol, name: i?.name, icon: i?.icon, price_usd: num(i?.price_usd), liquidity_usd: num(i?.liquidity_usd), mcap_usd: num(i?.mcap_usd) });

/* ---------- target weights of an index from its traders ---------- */
export function targetWeights(traderPortfolios, weights, rules = RULES()) {
  // traderPortfolios: [{rows}], weights: [w] summing to 1. Returns mint -> weight for tokens only; the rest is SOL (cash).
  const t = new Map();
  traderPortfolios.forEach((p, i) => {
    const w = weights[i] || 0;
    for (const r of p.rows) {
      if (r.mint === SOL || STABLES.has(r.mint)) continue;               // cash stays cash
      if (r.weight * 100 < rules.minWeight) continue;                      // dust and airdrops
      if (num(r.liquidity_usd) < rules.minLiquidity) continue;             // untradeable
      t.set(r.mint, (t.get(r.mint) || 0) + w * r.weight);
    }
  });
  const sorted = [...t.entries()].sort((a, b) => b[1] - a[1]).slice(0, rules.maxTokens);
  return new Map(sorted);
}

/* ---------- Jupiter swaps ---------- */
export async function quote(inputMint, outputMint, amountRaw, slippageBps) {
  const u = `${JUP}/swap/v1/quote?inputMint=${inputMint}&outputMint=${outputMint}&amount=${amountRaw}&slippageBps=${slippageBps}&restrictIntermediateTokens=true`;
  const r = await fetch(u); const j = await r.json();
  if (!r.ok || j.error) throw new Error('quote failed: ' + (j.error || r.status));
  return j;
}
export async function swap(keypair, quoteResponse) {
  const r = await fetch(`${JUP}/swap/v1/swap`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ quoteResponse, userPublicKey: keypair.publicKey.toBase58(), wrapAndUnwrapSol: true, dynamicComputeUnitLimit: true, dynamicSlippage: true, prioritizationFeeLamports: { priorityLevelWithMaxLamports: { maxLamports: 2000000, priorityLevel: 'high' } } }) });
  const j = await r.json();
  if (!r.ok || !j.swapTransaction) throw new Error('swap build failed: ' + (j.error || r.status));
  const tx = VersionedTransaction.deserialize(Buffer.from(j.swapTransaction, 'base64'));
  tx.sign([keypair]);
  const c = conn();
  const sig = await c.sendRawTransaction(tx.serialize(), { skipPreflight: true, maxRetries: 3 });
  const conf = await c.confirmTransaction({ signature: sig, blockhash: tx.message.recentBlockhash, lastValidBlockHeight: j.lastValidBlockHeight }, 'confirmed');
  if (conf.value.err) throw new Error('swap failed on-chain: ' + JSON.stringify(conf.value.err));
  return sig;
}
export async function decimalsOf(mint) {
  if (mint === SOL) return 9;
  const cached = (await tokensGet([mint])).get(mint);
  if (cached?.decimals != null) return cached.decimals;
  const info = await conn().getParsedAccountInfo(new PublicKey(mint));
  const d = info.value?.data?.parsed?.info?.decimals ?? 6;
  await tokenSet(mint, { decimals: d });
  return d;
}
export async function sendSol(keypair, to, lamports) {
  const tx = new Transaction().add(SystemProgram.transfer({ fromPubkey: keypair.publicKey, toPubkey: new PublicKey(to), lamports }));
  return sendAndConfirmTransaction(conn(), tx, [keypair], { commitment: 'confirmed' });
}
export const toRaw = (ui, decimals) => BigInt(Math.floor(ui * 10 ** decimals)).toString();
export { LAMPORTS_PER_SOL, PublicKey, bs58 };
