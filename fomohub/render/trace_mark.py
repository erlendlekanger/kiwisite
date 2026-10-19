"""Trace the fomo mark (1024px PNG) into polylines: outer silhouette + two pupil holes.
Writes mark.json with contours in normalized 0..1 coords (x right, y down), origin top-left."""
import sys, json
import numpy as np, cv2
from PIL import Image

src, out = sys.argv[1], sys.argv[2]
im = np.array(Image.open(src).convert('RGB')).astype(np.int32)
# white-ish pixels = the mark
mask = ((im[:, :, 0] > 150) & (im[:, :, 1] > 150) & (im[:, :, 2] > 150)).astype(np.uint8) * 255
H, W = mask.shape
contours, hier = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
hier = hier[0]
res = {'w': W, 'h': H, 'outer': [], 'holes': []}
def simp(c, eps):
    c2 = cv2.approxPolyDP(c, eps, True)
    return [[round(float(p[0][0]) / W, 5), round(float(p[0][1]) / H, 5)] for p in c2]
for i, c in enumerate(contours):
    area = cv2.contourArea(c)
    if area < 200: continue
    x, y, w, h = cv2.boundingRect(c)
    d = {'pts': simp(c, 0.8), 'bbox': [x / W, y / H, w / W, h / H], 'area': area / (W * H)}
    if hier[i][3] == -1: res['outer'].append(d)
    else: res['holes'].append(d)
res['holes'].sort(key=lambda d: d['bbox'][0])
json.dump(res, open(out, 'w'))
print('outer', [(len(o['pts']), o['bbox']) for o in res['outer']])
print('holes', [(len(o['pts']), o['bbox']) for o in res['holes']])
