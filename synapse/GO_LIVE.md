# Getting SYNAPSE_ live (from your always-on PC)

The game runs on your PC. A free tunnel gives it a public web address.
Vercel is optional (only if you want it on your own domain — see the bottom).

## What you need once
1. Install **cloudflared** (free, from Cloudflare). Windows: download the
   `cloudflared.exe` installer from Cloudflare's site, or run in PowerShell:
   `winget install --id Cloudflare.cloudflared`

## Every time you want to be live
1. **Double-click `start_public.bat`** (in this folder). A black window opens and
   stays open — that is the game running. It prints your **admin key**. Keep the
   window open.
2. Open a **second** terminal and run:
   `cloudflared tunnel --url http://localhost:8861`
3. It prints a public address like `https://something-random.trycloudflare.com`.
   **That address IS your live game.** Share it. Everything works from there:
   the site, the brain, the dream, buying land, everything.

That's it. Two windows open on your PC = you are live.

### Notes
- Keep both windows open and the PC awake (Settings > Power > never sleep).
- The `trycloudflare.com` address changes each time you restart the tunnel. For a
  fixed address, use a Cloudflare named tunnel with a domain you own (ask Claude).
- Admin panel: open `http://localhost:8861/admin` **on the PC itself** and enter
  the admin key printed in the black window.

## Optional: put it on your Vercel domain
1. Deploy this `synapse` folder to Vercel as a static site.
2. In `index.html` and `dream.html` (top of `<head>`), set
   `window.__SYN_API = "https://your-tunnel-address";`  (your PC's public URL).
3. Redeploy. The Vercel site now talks to the game on your PC.
   (Ask Claude to wire the `/dream` route + `/pfp.png` if the feed avatar 404s.)
