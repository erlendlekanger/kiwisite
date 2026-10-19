// Postgres access. One pool per function instance; the schema is created on first use.
import pg from 'pg';

let pool, ready;
export function db() {
  if (!pool) {
    if (!process.env.DATABASE_URL) throw new Error('DATABASE_URL is not set');
    pool = new pg.Pool({ connectionString: process.env.DATABASE_URL, max: Number(process.env.PG_POOL_MAX || 3), ssl: process.env.DATABASE_URL.includes('localhost') ? false : { rejectUnauthorized: false } });
  }
  return pool;
}

export async function q(text, params = []) {
  await init();
  const r = await db().query(text, params);
  return r.rows;
}

export function init() {
  if (!ready) ready = db().query(SCHEMA);
  return ready;
}

const SCHEMA = `
CREATE TABLE IF NOT EXISTS users (
  wallet TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS traders (
  handle TEXT PRIMARY KEY,
  name TEXT,
  wallet TEXT,
  avatar TEXT,
  rank INT,
  pnl_24h NUMERIC, pnl_7d NUMERIC, pnl_30d NUMERIC,
  source TEXT DEFAULT 'manual',
  active BOOLEAN DEFAULT true,
  positions JSONB,
  positions_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS indexes (
  id TEXT PRIMARY KEY,
  owner TEXT REFERENCES users(wallet),
  name TEXT NOT NULL,
  traders JSONB NOT NULL,
  deposit_pubkey TEXT NOT NULL,
  secret_enc TEXT NOT NULL,
  status TEXT DEFAULT 'active',
  deposited_sol NUMERIC DEFAULT 0,
  withdrawn_sol NUMERIC DEFAULT 0,
  last_rebalance TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS snapshots (
  id BIGSERIAL PRIMARY KEY,
  index_id TEXT REFERENCES indexes(id),
  ts TIMESTAMPTZ DEFAULT now(),
  nav_sol NUMERIC, nav_usd NUMERIC, sol_usd NUMERIC,
  holdings JSONB
);
CREATE INDEX IF NOT EXISTS snapshots_idx ON snapshots(index_id, ts);
CREATE TABLE IF NOT EXISTS trades (
  id BIGSERIAL PRIMARY KEY,
  index_id TEXT REFERENCES indexes(id),
  ts TIMESTAMPTZ DEFAULT now(),
  side TEXT, mint TEXT, symbol TEXT,
  amount_sol NUMERIC, amount_token NUMERIC, price_usd NUMERIC,
  sig TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS events (
  id BIGSERIAL PRIMARY KEY,
  index_id TEXT,
  ts TIMESTAMPTZ DEFAULT now(),
  level TEXT, message TEXT, data JSONB
);
CREATE TABLE IF NOT EXISTS nonces (
  nonce TEXT PRIMARY KEY,
  wallet TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS token_cache (
  mint TEXT PRIMARY KEY,
  symbol TEXT, name TEXT, icon TEXT, decimals INT,
  liquidity_usd NUMERIC, price_usd NUMERIC, mcap_usd NUMERIC,
  updated_at TIMESTAMPTZ DEFAULT now()
);
`;

export async function log(index_id, level, message, data) {
  try { await q('INSERT INTO events(index_id, level, message, data) VALUES ($1,$2,$3,$4)', [index_id, level, message, data ? JSON.stringify(data) : null]); } catch (e) { /* logging never fails the request */ }
}
