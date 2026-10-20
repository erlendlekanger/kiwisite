"""The PACKHUNT astronaut (packhunt/tools/astronaut_compose.py, same cut-out and dark visor) with the FOMOINDEX iPhone
(render/iphone.py, 4K Blender render) drifting at the reaching glove where the PACKHUNT pack was.

    py fomoindex/render/astronaut_ph_compose.py <source png> <out png> --item <png> [--pack x,y,w,angle] [--visor paint|keep]  (keep = the source already has its visor, e.g. visor_inpaint.py; only make the glass opaque)

x,y = where the pack's centre lands (in source pixels), w = pack width in pixels, angle in degrees (counter-clockwise).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter
from rembg import new_session, remove
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
src_path, out_path = sys.argv[1], sys.argv[2]
args = sys.argv[3:]


def opt(name, default=None):
    return args[args.index(name) + 1] if name in args else default


im = Image.open(src_path).convert("RGB")
W, H = im.size

# cover patches (insignia) with blurred suit fabric sampled just beside them
covers = [a for i, a in enumerate(args) if i > 0 and args[i - 1] == "--cover"]
for c in covers:
    x0, y0, x1, y1 = [int(v) for v in c.split(",")]
    w, h = x1 - x0, y1 - y0
    sample = im.crop((x0 - w, y0, x0, y1)) if x0 - w >= 0 else im.crop((x1, y0, x1 + w, y1))
    im.paste(sample.filter(ImageFilter.GaussianBlur(2)), (x0, y0))

mask_src = im.copy()
# a dark visor: an ellipse over the glass, keeping only a little of its sheen so nobody is visible inside
vz = opt("--visor")
if vz:
    # The glass follows the inner edge of the helmet ring, traced on a gridded zoom of astro_c_100_hires.png
    # (the old tilted ellipse missed the left half of the opening, where the face is, and ran over the ring).
    import cv2
    ring = np.array([(1135, 790), (1158, 752), (1186, 724), (1218, 700), (1256, 684), (1300, 674), (1340, 672),
                     (1378, 680), (1410, 694), (1428, 716), (1430, 770), (1430, 820), (1424, 870), (1412, 912),
                     (1396, 945), (1374, 970), (1350, 989), (1326, 1003), (1288, 1008), (1250, 1007), (1214, 1003),
                     (1182, 992), (1156, 970), (1137, 945), (1124, 910), (1119, 872), (1122, 834)], np.int32)
    poly = np.zeros((H, W), np.uint8)
    cv2.fillPoly(poly, [ring], 255)
    m2 = cv2.GaussianBlur(poly.astype(np.float32) / 255, (0, 0), 1.4)
    m = m2[..., None]
    visor_mask = m2   # the glass is solid: nothing shows through it
if vz == "paint":
    cx, cy, rr = 1281.0, 852.0, 162.0
    yy, xx = np.mgrid[0:H, 0:W]
    nx, ny = (xx - cx) / rr, (yy - cy) / rr
    r2 = np.clip(nx ** 2 + ny ** 2, 0, 1)
    nz = np.sqrt(1 - r2)
    arr = np.asarray(im).astype(np.float32)
    # black glass: nearly black, a faint lift where the dome faces the key light, a thin dark-grey fresnel rim
    # and two small soft highlights up to the left, like a real black-tinted EVA visor
    L = np.array([-0.45, -0.62, 0.64]); L = L / np.linalg.norm(L)
    lam = np.clip(nx * L[0] + ny * L[1] + nz * L[2], 0, 1)
    col = np.full((H, W, 3), 4.0, np.float32)
    col += (lam ** 3)[..., None] * np.array([16, 17, 20], dtype=np.float32)
    col += ((1 - nz) ** 4)[..., None] * np.array([40, 42, 48], dtype=np.float32)
    hl1 = np.exp(-(((nx + 0.40) / 0.15) ** 2 + ((ny + 0.50) / 0.07) ** 2))
    hl2 = np.exp(-(((nx + 0.58) / 0.045) ** 2 + ((ny + 0.28) / 0.045) ** 2))
    col += (hl1 * 0.55 + hl2 * 0.7)[..., None] * np.array([235, 238, 242], dtype=np.float32)
    arr = arr * (1 - m) + col * m
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

sess = new_session("isnet-general-use")
mask = np.asarray(remove(mask_src, session=sess, only_mask=True).convert("L")).astype(np.float32) / 255.0   # from the untouched image, so the dark visor stays solid
hard = mask > 0.35
labels, n = ndimage.label(hard)
if n > 1:
    sizes = ndimage.sum(hard, labels, range(1, n + 1))
    keep = labels == (int(np.argmax(sizes)) + 1)
    mask = mask * keep
    print("blobs", n, "kept the largest", flush=True)
mask = np.clip((mask - 0.08) / 0.84, 0, 1)
if vz:
    mask = np.maximum(mask, visor_mask)
alpha = Image.fromarray((mask * 255).astype(np.uint8))
out = im.convert("RGBA")
out.putalpha(alpha)

# the real pack
pk = opt("--pack")
if pk:
    x, y, w, ang = [float(v) for v in pk.split(",")]
    pack = Image.open(opt("--item")).convert("RGBA")
    pack = pack.crop(pack.getchannel("A").getbbox())
    pack = pack.resize((int(w), int(pack.height * w / pack.width)), Image.LANCZOS).rotate(ang, expand=True, resample=Image.BICUBIC)
    # no drop shadow: in open space there is nothing behind the phone to catch one
    out.alpha_composite(pack, (int(x - pack.width / 2), int(y - pack.height / 2)))

a = out.getchannel("A").point(lambda v: 255 if v > 6 else 0)
bb = a.getbbox()
out = out.crop(bb)
pad = int(max(out.size) * 0.02)
final = Image.new("RGBA", (out.width + 2 * pad, out.height + 2 * pad), (0, 0, 0, 0))
final.paste(out, (pad, pad))
final.save(out_path, optimize=True)
print("wrote", out_path, final.size, os.path.getsize(out_path) // 1024, "KB", flush=True)
