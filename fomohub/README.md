# FOMOHUB

Everything fomo in one place. A static site: `index.html`, `app.css`, `app.js`, `mascot.js` and the
rendered artwork in `assets/`. Hash routes (`#/spend`, `#/leaderboard`, ...) so it runs from any folder
or as its own Vercel project with this directory as the root.

## The mascot

The mark in the middle is the official fomo mark, traced from the fomo favicon and rendered in 3D with
Blender (Cycles, path traced) by `render/render_mascot.py`. The body and the two pupils are rendered
separately; `mascot.js` holds where the pupils sit in the frame, and `app.js` moves them toward the
pointer, blinks them and leans the whole mark a little. The six icons come from `render/render_icons.py`.

To render again: `pip install bpy opencv-python-headless`, then

    python3 render/trace_mark.py fomo-favicon.png render/mark.json
    python3 render/render_mascot.py render/mark.json assets/mascot 160
    python3 render/render_icons.py assets/icons 160

## Plugging in the backends

`app.js` starts with a `CONFIG` block:

- `spendApi`: the spend.family engine. While it is `null` the checkout is shown but the pay buttons wait.
- `fantasyUrl`: the fomofantasy app. While it is `null` the page explains the game and says it opens soon.
- `leaderboardApi`: `api/leaderboard.mjs` proxies fomo's `/v2/leaderboard`, which needs a fomo session.
  Set `FOMO_API_TOKEN` or `FOMO_COOKIE` on the deployment and the live board appears; without it the page
  links to fomo.family/leaderboard (fomo does not allow the site in an iframe).

FOMOPREDICT uses the Coinbase spot price with DexScreener as a fallback. FOMORADAR uses DexScreener's
boosted tokens and links each token to its page on fomo. FOMOQUESTS keeps its state in the browser.
