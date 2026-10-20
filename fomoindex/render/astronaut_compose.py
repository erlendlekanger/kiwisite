"""Turns the chosen FLUX astronaut into the front-page image: the FOMOINDEX screen goes into the phone he holds out,
his glove is laid back over it, the reflected text in the visor is painted out, and he is cut free from the
background (hard rembg mask, largest blob only, so the earth behind him goes).

    py fomoindex/render/astronaut_compose.py <hires png> <screen png> <out dir>

The glass corners and the visor box are measured on astro_p_102_hires.png; another candidate needs new numbers.

Writes astronaut.webp (site) and astronaut-4k.png (full resolution, transparent) into <out dir>.
"""
import os
import sys

import cv2
import numpy as np
from PIL import Image
from rembg import new_session, remove
from scipy import ndimage

src_path, screen_path, out_dir = sys.argv[1], sys.argv[2], sys.argv[3]
im = np.asarray(Image.open(src_path).convert("RGB")).copy()
H, W = im.shape[:2]
lum = im.mean(axis=2)

# ---- 1. the reflected «NASA» in the visor: inpaint the bright letters from the dark glass around them
vx0, vy0, vx1, vy1 = 1110, 672, 1264, 737           # just the letters; the rim reflections left of them stay
letters = np.zeros((H, W), np.uint8)
letters[vy0:vy1, vx0:vx1] = (lum[vy0:vy1, vx0:vx1] > 95).astype(np.uint8) * 255
letters = cv2.dilate(letters, np.ones((7, 7), np.uint8))
im = cv2.inpaint(im, letters, 5, cv2.INPAINT_TELEA)
lum = im.mean(axis=2)

# ---- 2. the phone's glass, read off a gridded zoom of the hires image (TL, TR, BR, BL). Detecting the dark slab
# automatically also caught the shadow between thumb and phone and put the screen too far left.
quad = np.float32([[768, 890], [1139, 888], [1158, 1677], [790, 1679]])
hull = quad.round().astype(np.int32).reshape(-1, 1, 2)
c = quad.mean(0)

# ---- 3. the screen, with rounded corners, warped onto the glass
scr = Image.open(screen_path).convert("RGB")
sw, sh = scr.size
r = int(sw * 0.11)
rmask = Image.new("L", (sw, sh), 0)
from PIL import ImageDraw
ImageDraw.Draw(rmask).rounded_rectangle((0, 0, sw - 1, sh - 1), r, fill=255)
scr_rgba = np.dstack([np.asarray(scr), np.asarray(rmask)])
M = cv2.getPerspectiveTransform(np.float32([[0, 0], [sw, 0], [sw, sh], [0, sh]]), quad)
warped = cv2.warpPerspective(scr_rgba, M, (W, H), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
a = warped[..., 3:4].astype(np.float32) / 255
# a faint diagonal sheen on the glass so it reads as a lit screen under the same key light
yy, xx = np.mgrid[0:H, 0:W]
sheen = np.clip(1 - np.abs((xx - c[0]) * 0.55 + (yy - c[1]) * 0.25 + 120) / 260, 0, 1)[..., None] * 0.07
screen_rgb = np.clip(warped[..., :3].astype(np.float32) / 255 + sheen, 0, 1)

# ---- 4. the glove goes back on top. The glass is almost black (luminance about 8) and even the shaded folds of the
# glove are brighter, so everything brighter inside the glass that reaches in from its left edge is fingers.
hull_mask = np.zeros((H, W), np.uint8)
cv2.fillConvexPoly(hull_mask, hull, 255)
fingers = ((lum > 14) & (hull_mask > 0)).astype(np.uint8)
fingers = cv2.morphologyEx(fingers, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
lab, n = ndimage.label(fingers)
left_edge = np.zeros((H, W), bool)
for y in range(H):
    row = np.where(hull_mask[y] > 0)[0]
    if row.size:
        left_edge[y, row[0]:row[0] + 14] = True
keep = [i for i in range(1, n + 1) if (lab == i).sum() > 1500 and (left_edge & (lab == i)).any()]
fingers = ndimage.binary_fill_holes(np.isin(lab, keep))
fingers = cv2.GaussianBlur(fingers.astype(np.float32), (0, 0), 1.2)[..., None]
cover = a * (1 - fingers)
base = im.astype(np.float32) / 255
out = base * (1 - cover) + screen_rgb * cover
im = (np.clip(out, 0, 1) * 255).round().astype(np.uint8)

# ---- 5. cut him out; keep only the biggest piece so the earth below goes
sess = new_session("isnet-general-use")
cut = remove(Image.fromarray(im), session=sess, only_mask=True)
m = np.asarray(cut) > 128
lab, n = ndimage.label(m)
m = lab == (np.argmax(np.bincount(lab.ravel())[1:]) + 1)
m = ndimage.binary_fill_holes(m)
alpha = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.1)
rgba = np.dstack([im, (alpha * 255).round().astype(np.uint8)])
ys, xs = np.where(alpha > 0.02)
pad = 24
crop = rgba[max(0, ys.min() - pad):ys.max() + pad, max(0, xs.min() - pad):xs.max() + pad]

os.makedirs(out_dir, exist_ok=True)
full = Image.fromarray(crop, "RGBA")
full.save(os.path.join(out_dir, "astronaut-4k.png"), optimize=True)
site = full.copy()
if site.width > 1800:
    site = site.resize((1800, round(site.height * 1800 / site.width)), Image.LANCZOS)
site.save(os.path.join(out_dir, "astronaut.webp"), quality=90, method=6)
print("saved", full.size, site.size)
