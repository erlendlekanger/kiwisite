# STONKD

Merkevaren til STONKD (tidligere STONKED), en extension av StonkFun.

## brand/

Logoen «Stack»: fem stablede piller som tegner en punktsymmetrisk S, fra
`#ccedf9` øverst til `#52b9e2` nederst.

| Fil | Bruk |
|---|---|
| `stonkd-mark.svg` | Merket alene, gjennomsiktig. Til nettsiden. |
| `stonkd-logo-square.svg`, `stonkd-logo-4096.png`, `stonkd-logo-1024.png` | 1:1 på svart |
| `stonkd-logo-square-transparent.svg`, `stonkd-logo-transparent-2048.png` | 1:1 uten bakgrunn |
| `stonkd-icon.svg`, `icon-512.png`, `apple-touch-icon-180.png`, `favicon-32.png`, `favicon.ico` | Ikoner, merket fyller mer av flaten |

`cd brand && python3 build.py` lager SVG-ene på nytt.

## render/

Myntene i Blender (Cycles). Krever `pip install bpy`.

    python3 render/coin_render.py out.png 3840 2160 128

`render/output/stonkd-hero-4k.png` er hero-bildet: frostet glassmynt med
Stack-merket i emalje, en Apple-mynt i stål og en SOL-mynt.
