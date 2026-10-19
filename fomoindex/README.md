# FOMOINDEX

Build an index of fomo traders and fund it with SOL. The index mirrors what the traders hold on-chain,
blended by the weights you chose, and rebalances every 30 minutes through Jupiter.

- `index.html` landing, `app.html` + `app.js` the app, `styles.css`, `space.js` the starfield.
- `api/` Vercel Node functions (ESM), `lib/` the engine. `render/` the Blender scripts for the logo and the astronaut.

## Setup

1. Create a Vercel project from this repo with **Root Directory = fomoindex**.
2. Add the environment variables from `.env.example`. `MASTER_KEY` must be 32 random bytes as hex
   (`openssl rand -hex 32`); it encrypts every index wallet, so back it up and never rotate it casually.
3. Postgres: Neon, Supabase or Vercel Postgres. Tables are created on first request.
4. RPC: a Helius key in `RPC_URL`. The public RPC works for testing but rate-limits.
5. Ticker: Vercel's free plan runs crons once a day, so `.github/workflows/fomoindex-cron.yml` (repo root)
   calls `/api/cron/sync-traders` and `/api/cron/rebalance` every 30 minutes. Set the repo secrets
   `FOMOINDEX_URL` and `FOMOINDEX_CRON_SECRET`. On Vercel Pro you can use Vercel Cron instead.

## Traders

A trader can be mirrored once we know their wallet. Two sources:

- `FOMO_API_TOKEN` / `FOMO_COOKIE`: `/api/cron/sync-traders` pulls the fomo leaderboard and stores
  handle, name, avatar, rank, 7d PnL, plus the wallet if the API exposes one.
- Manual: `POST /api/admin/traders` with `Authorization: Bearer ADMIN_KEY` and either
  `{"traders":[{"handle":"chang","wallet":"4k3D…"}]}` or `{"csv":"handle,wallet\nchang,4k3D…"}`.

## How the engine works

- `lib/solana.mjs`: balances (both token programs), prices and liquidity (DexScreener, cached 10 min),
  SOL price (Jupiter), Jupiter quote + swap, SOL transfers, AES-256-GCM custody of index keys.
- `targetWeights()`: for each trader, holdings as a share of their wallet; drop SOL and stables (cash),
  anything under `MIN_WEIGHT_PCT`, anything under `MIN_LIQUIDITY_USD`; blend by the index weights;
  keep the top `MAX_TOKENS_PER_INDEX`.
- `lib/index.mjs rebalance()`: compares the index wallet to the target, sells what is over by more than
  `REBALANCE_THRESHOLD_PCT`, then buys what is under with SOL, writes trades and a NAV snapshot.
- `liquidate()`: sells everything to SOL and sends it to the owner's wallet (withdraw).

## Endpoints

| route | what |
| --- | --- |
| `POST /api/auth/nonce`, `POST /api/auth/verify`, `GET/DELETE /api/auth/me` | sign in with a wallet signature |
| `GET /api/traders`, `GET /api/traders/:handle/positions` | leaderboard, live portfolio |
| `GET/POST /api/index`, `GET /api/index/:id` | my indexes, create, detail |
| `POST /api/index/:id/deposit {sig}` | record a SOL deposit |
| `POST /api/index/:id/status {status}` | pause / resume |
| `POST /api/index/:id/withdraw` | sell all and send SOL to the owner |
| `GET /api/cron/rebalance`, `GET /api/cron/sync-traders` | the ticker (CRON_SECRET) |
| `POST /api/admin/traders` | add traders (ADMIN_KEY) |
| `GET /api/health` | config check |

Custodial by design for v1: each index has its own wallet whose key lives encrypted in the database.
A non-custodial vault program is the planned v2.
