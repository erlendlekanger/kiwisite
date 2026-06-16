"""Regenerate public/index.html from the canonical game.py PAGE template.

Run from the repo root (one level above this folder) or from here:
    python build.py
"""
import importlib.util
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GAME_PY = os.path.normpath(os.path.join(HERE, "..", "game.py"))
OUT = os.path.join(HERE, "public", "index.html")


def main():
    spec = importlib.util.spec_from_file_location("game", GAME_PY)
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    html = (
        g.PAGE
        .replace("__MINT__", g.COIN)
        .replace("__MIN_HOLD__", str(g.MIN_HOLD_AMOUNT))
        .replace("__SAVE_VER__", g.SAVE_VERSION)
        .replace("__INTRO_VER__", g.INTRO_VERSION)
        .replace("__TUTORIAL_VER__", g.TUTORIAL_VERSION)
    )
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {OUT} ({len(html):,} bytes)  coin={g.COIN}  min={g.MIN_HOLD_AMOUNT}")


if __name__ == "__main__":
    main()
