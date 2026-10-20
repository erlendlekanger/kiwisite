"""FOMOINDEX 1:1 logo: the wave background (waves_bg.html) with the FOMOINDEX wordmark in the middle.

  py fomoindex/brand/render_logo.py  -> fomoindex/brand/fomoindex-logo-1x1.png (1254) and -512.png
"""
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
W = 1254


def main() -> None:
    bg_png = HERE / "_waves_bg.png"
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=d3d11", "--enable-gpu", "--ignore-gpu-blocklist", "--mute-audio"])
        pg = b.new_page(viewport={"width": W, "height": W}, device_scale_factor=1)
        pg.goto((HERE / "waves_bg.html").as_uri())
        pg.wait_for_function("document.title === 'ready'")
        pg.locator("#c").screenshot(path=str(bg_png))
        b.close()
    bg = Image.open(bg_png).convert("RGBA")
    # the wordmark at the size and tint the FOMOFANTASY logo uses: mark 219 px high, colour #EEF0FF
    wm = Image.open(HERE.parent / "assets" / "wordmark.png").convert("RGBA")
    s = 219 / 248
    wm = wm.resize((round(wm.width * s), 219), Image.LANCZOS)
    col = Image.new("RGBA", wm.size, (238, 240, 255, 255))
    col.putalpha(wm.getchannel("A"))
    bg.alpha_composite(col, ((W - wm.width) // 2, 509))
    out = bg.convert("RGB")
    out.save(HERE / "fomoindex-logo-1x1.png")
    out.resize((512, 512), Image.LANCZOS).save(HERE / "fomoindex-logo-512.png")
    bg_png.unlink()
    print("saved", HERE / "fomoindex-logo-1x1.png")


if __name__ == "__main__":
    main()
