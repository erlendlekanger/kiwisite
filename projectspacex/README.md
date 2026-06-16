# PROJECT SPACEX

Isometric idle game. Connect a Phantom wallet holding **$SPACEX** (or play for
free) to build a base on Earth and set your sights on Mars.

## How it works on Vercel

- `public/index.html` + `public/assets/**` — the whole game (static).
- `api/balance.py` — `GET /api/balance?wallet=<pubkey>` returns the wallet's
  $SPACEX balance via Solana RPC. Polled every 30s by the client and instantly
  on wallet connect.
- `api/config.py` — `GET /api/config` returns token + threshold info.

Each player's progress is saved per wallet in their own browser (`localStorage`),
so every player only sees their own game.

## Environment variables (Settings → Environment Variables)

| Name | Default | Purpose |
|------|---------|---------|
| `GAME_COIN` | `9uJy4KWMbrxmA5kUtJSJPenZHK5mzd4BzbggNVdRXWh2` | pump.fun CA shown to users |
| `GAME_SPL_MINT` | `6tqz6vbw8vaxQtEJC2GvfMZ5ppthvYsyRJQNYPx5pump` | SPL mint used for balances |
| `GAME_MIN_HOLD` | `1000` | Tokens required for real mode |
| `SOLANA_RPC` | _(none)_ | Optional private RPC (e.g. Helius) to avoid public rate limits at scale |

## Regenerate index.html from game.py

```bash
python build.py
```

## Local dev

```bash
npx vercel dev
```
