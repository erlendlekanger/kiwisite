"""PAMPS — Pump Agent Modeling System, local preview server.

Run:  py pamps.py
Open: http://127.0.0.1:8811/

A simple static server (same shape as gtacasino.py): it just serves the
`pamps/` folder. The whole experience is driven client-side in index.html —
5 specialist "agents" co-training on a live pump.fun launch feed, with
volume / vision / holder / social / rug-defense signals streaming in real time.

Drop Gemini renders into pamps/assets/ to light up the office + avatars:
  pamps/assets/pamps_office.png   (the isometric Agent House hero)
  pamps/assets/agent_volt.png     (⚡ green pill)
  pamps/assets/agent_prism.png    (🎨 purple pill)
  pamps/assets/agent_sentinel.png (🛡️ red pill)
  pamps/assets/agent_oracle.png   (🔮 blue pill)
  pamps/assets/agent_hype.png     (📡 orange pill)
"""
from __future__ import annotations

import os
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "pamps"
PORT = int(os.environ.get("PORT", "8811"))
HOST = os.environ.get("HOST", "127.0.0.1")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, fmt: str, *args) -> None:
        pass  # quiet

    def end_headers(self) -> None:
        # no-store so edits + the live.json feed always refresh
        if self.path.endswith((".html", ".js", ".css")) or "live.json" in self.path or "search.json" in self.path:
            self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main() -> None:
    if not ROOT.is_dir():
        raise SystemExit(f"Missing folder: {ROOT}")
    os.chdir(ROOT)
    url = f"http://{HOST if HOST != '0.0.0.0' else '127.0.0.1'}:{PORT}/"
    print(f"PAMPS: {url}")
    print("Serving pamps/ — drop Gemini art into pamps/assets/ to light up the office.")
    if os.environ.get("PAMPS_NO_BROWSER") != "1" and HOST == "127.0.0.1":
        try:
            webbrowser.open(url)
        except OSError:
            pass
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
