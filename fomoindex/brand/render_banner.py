"""FOMOINDEX X banner, 1500x500: the logo on the left; on the right the site's own "Your index" box with five of
fomo's most popular traders, and in front of it the site's white card holding a three-trader index.
Both are screenshots of the real app (its CSS), not redrawn.

Needs the local dev server (preview "fomoindex", port 8796).
  py fomoindex/brand/render_banner.py  -> fomoindex/brand/fomoindex-banner-1500x500.png and -3000x1000.png
"""
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
S = 2
W, H = 1500 * S, 500 * S
WEIGHTS = [10, 8, 6, 5, 4]                       # example weights on the dark box's sliders
CARD = [("frankdegods", 45), ("unipcs", 35), ("seyong", 20)]   # the white card's three traders, example weights

PREP = """async (ws) => {
  const rows = [...document.querySelectorAll('tbody tr.row')].slice(0, 5);
  for (const r of rows) { r.querySelector('.chk').click(); await new Promise((x) => setTimeout(x, 150)); }
  document.querySelectorAll('.wrow input').forEach((el, i) => { el.value = ws[i]; el.dispatchEvent(new Event('input', { bubbles: true })); });
  document.getElementById('box').style.display = 'none';
  const panel = document.getElementById('panel');
  [...panel.querySelectorAll(':scope > .panel-b')].slice(1).forEach((el) => el.remove());
  panel.querySelector('#equal')?.parentElement.remove();
  panel.querySelectorAll('.wrow .x').forEach((el) => el.remove());
  document.getElementById('spacebg')?.remove();
  document.documentElement.style.background = document.body.style.background = 'transparent';
}"""

CARD_JS = """async (card) => {
  const by = {};
  for (const [h] of card) { const r = await (await fetch('/api/traders?limit=5&q=' + h)).json(); for (const t of r.traders) by[t.handle.toLowerCase()] = t; }
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const ts = card.map(([h, w]) => ({ ...(by[h.toLowerCase()] || { handle: h }), w }));
  const host = document.createElement('div');
  host.id = 'wcard'; host.style.cssText = 'position:fixed;left:40px;top:40px;width:330px;z-index:999';
  host.innerHTML = `<div class="tbox" style="animation:none"><div class="tbox-in">
    <div class="tbox-top"><img src="assets/mark-navy.svg" alt=""><span class="s">FOMO INDEX</span><span style="width:26px"></span></div>
    <div class="tbox-hero" style="padding-bottom:2px">
      <div style="display:flex">${ts.map((t, i) => `<div class="tbox-art" style="width:58px;height:58px;margin-left:${i ? -18 : 0}px;border:3px solid #f2f3f6;position:relative;z-index:${5 - i}"><img src="${esc(t.avatar)}" alt=""></div>`).join('')}</div>
      <div class="tbox-h"><b>Legends</b><small>3 fomo traders</small></div>
    </div>
    <div class="tbox-stats"><div><small>Traders</small><b>3</b></div><div><small>Mirrors</small><b>2 h</b></div><div><small>Fee</small><b>0.5%</b></div></div>
    <div class="tbox-sec"><div class="lbl">Weights</div><div class="tbox-hold" style="--c:22px 112px 1fr 40px">${ts.map((t) => `<div style="grid-template-columns:var(--c)"><i><img src="${esc(t.avatar)}" alt=""></i><b>@${esc(t.handle)}</b><div class="bar"><em style="width:${t.w}%"></em></div><small>${t.w}%</small></div>`).join('')}</div></div>
    <div class="tbox-foot"><div class="meta">fomoindex.app</div><button class="btn sm">Fund index</button></div>
  </div></div>`;
  document.body.appendChild(host);
}"""


def shoot(panel_path: Path, card_path: Path) -> None:
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--mute-audio"])
        pg = b.new_page(viewport={"width": 1440, "height": 1400}, device_scale_factor=S)
        pg.goto("http://localhost:8796/app#build")
        pg.wait_for_selector("tbody tr.row .chk")
        pg.evaluate(PREP, WEIGHTS)
        pg.evaluate(CARD_JS, CARD)
        pg.wait_for_timeout(3000)                 # avatars
        pg.locator("#panel").screenshot(path=str(panel_path), omit_background=True)
        pg.locator("#wcard .tbox").screenshot(path=str(card_path), omit_background=True)
        b.close()


def fit(img: Image.Image, h: int) -> Image.Image:
    return img.resize((round(img.width * h / img.height), h), Image.LANCZOS)


def main() -> None:
    ps, cs = HERE / "_panel.png", HERE / "_card.png"
    shoot(ps, cs)
    bg = Image.new("RGBA", (W, H), (10, 10, 38, 255))
    wm = Image.open(HERE.parent / "assets" / "wordmark.png").convert("RGBA")
    mh = 104 * S
    wm = fit(wm, mh)
    col = Image.new("RGBA", wm.size, (238, 240, 255, 255))
    col.putalpha(wm.getchannel("A"))
    bg.alpha_composite(col, (100 * S, (H - mh) // 2))
    panel = fit(Image.open(ps).convert("RGBA"), 400 * S)
    px = W - panel.width - 70 * S
    bg.alpha_composite(panel, (px, (H - panel.height) // 2 - 10 * S))
    # the white card in front, overlapping the left of the dark box, tilted a little
    card = fit(Image.open(cs).convert("RGBA"), 420 * S).rotate(4, resample=Image.BICUBIC, expand=True)
    bg.alpha_composite(card, (px - card.width + 120 * S, (H - card.height) // 2 + 4 * S))
    out = bg.convert("RGB")
    out.save(HERE / "fomoindex-banner-3000x1000.png")
    out.resize((1500, 500), Image.LANCZOS).save(HERE / "fomoindex-banner-1500x500.png")
    ps.unlink()
    cs.unlink()


if __name__ == "__main__":
    main()
