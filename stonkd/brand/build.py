"""STONKD-logoen «Stack»: fem stablede piller som tegner en S.

Radene er punktsymmetriske (rad 0 speiler rad 4, rad 1 speiler rad 3), saa S-en
staar i balanse. Fargene gaar fra #ccedf9 oeverst til #52b9e2 nederst.
"""
H, GAP, W = 78, 28, 400                 # pillehoeyde, mellomrom, bredde paa S-en
ROWS = [(0.20, 1.00), (0.00, 0.45), (0.15, 0.85), (0.55, 1.00), (0.00, 0.80)]
TOP, BOT = (0xcc, 0xed, 0xf9), (0x52, 0xb9, 0xe2)


def col(t):
    return "#" + "".join(f"{round(a + (b - a) * t):02x}" for a, b in zip(TOP, BOT))


def bars(x0, y0, s=1.0):
    out = []
    for i, (a, b) in enumerate(ROWS):
        out.append(f'<rect x="{x0 + a * W * s:g}" y="{y0 + i * (H + GAP) * s:g}" width="{(b - a) * W * s:g}" '
                   f'height="{H * s:g}" rx="{H * s / 2:g}" fill="{col(i / 4)}"/>')
    return "\n  ".join(out)


TALL = 5 * H + 4 * GAP                   # 502


def mark_svg():
    """Bare merket, gjennomsiktig, stramt utsnitt. Til nettsiden."""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {TALL}" width="{W}" height="{TALL}">\n  '
            f'{bars(0, 0)}\n</svg>\n')


def square_svg(size=1000, fill=0.5, bg="#000000"):
    """1:1 med merket midt i. fill = andel av hoeyden merket tar."""
    s = size * fill / TALL
    x0 = (size - W * s) / 2
    y0 = (size - TALL * s) / 2
    rect = f'<rect width="{size}" height="{size}" fill="{bg}"/>\n  ' if bg else ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="{size}" height="{size}">\n  '
            f'{rect}{bars(x0, y0, s)}\n</svg>\n')


open("stonkd-mark.svg", "w").write(mark_svg())
open("stonkd-logo-square.svg", "w").write(square_svg())
open("stonkd-icon.svg", "w").write(square_svg(fill=0.66))           # favicon/app: merket fyller mer
open("stonkd-logo-square-transparent.svg", "w").write(square_svg(bg=None))
print("ok")
