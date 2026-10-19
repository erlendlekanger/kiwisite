"""Render the official fomo mark as a glossy 3D mascot: body (the mark, with its cut-outs) + two pupils.
usage: python3 -I render_mascot.py mark.json outdir [samples] [res_scale]"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, numpy as np, cv2
from mathutils import Vector
from PIL import Image
import fomorender as F

markf, outdir = sys.argv[1], sys.argv[2]
SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 192
RES = float(sys.argv[4]) if len(sys.argv) > 4 else 1.0
os.makedirs(outdir, exist_ok=True)
mark = json.load(open(markf))
W, H = mark['w'], mark['h']
outer = max(mark['outer'], key=lambda o: o['area'])
hole = mark['holes'][0]

# pupil shape: the right-hand cut-out as a quad; the left pupil is the same shape in the left socket
hc = np.array([[p[0] * W, p[1] * H] for p in hole['pts']], np.float32).reshape(-1, 1, 2)
quad = cv2.approxPolyDP(hc, 12, True).reshape(-1, 2).tolist()
quad = [q for q in quad if not (abs(q[0] - 455) < 8 and abs(q[1] - 513) < 8)]  # drop the tiny kink on the left side
qc = [sum(q[0] for q in quad) / len(quad), sum(q[1] for q in quad) / len(quad)]
CENTERS = [[233.8, 508.9], [579.9, 509.5]]   # centroids of the two dark sockets (left, right), image px
PUPIL_SCALE = 0.66
def pupil_pts(c):
    return [[c[0] + (q[0] - qc[0]) * PUPIL_SCALE, c[1] + (q[1] - qc[1]) * PUPIL_SCALE] for q in quad]

# normalise: mark width -> 4.0 units, centred at origin, lying in the XY plane facing +Z
bx, by, bw, bh = outer['bbox']
S = 4.0 / (bw * W)
cx, cy = (bx + bw / 2) * W, (by + bh / 2) * H
def P(p): return ((p[0] - cx) * S, -(p[1] - cy) * S)
outer_px = [[p[0] * W, p[1] * H] for p in outer['pts']]
hole_px = [[p[0] * W, p[1] * H] for p in hole['pts']]

sc = F.reset()
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'
sc.world.node_tree.nodes['Background'].inputs[1].default_value = 1.0

def curve_obj(name, loops, extrude, bevel, res=8, z=0.0, round_corners=0):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '2D'; cu.fill_mode = 'BOTH'
    cu.extrude = extrude; cu.bevel_depth = bevel; cu.bevel_resolution = res; cu.resolution_u = 6
    for pts in loops:
        if round_corners:   # bezier with auto handles gives softly rounded corners on the pupils
            sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts) - 1)
            for i, p in enumerate(pts):
                x, y = P(p); b = sp.bezier_points[i]; b.co = (x, y, 0)
                b.handle_left_type = b.handle_right_type = 'AUTO'
        else:
            sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
            for i, p in enumerate(pts):
                x, y = P(p); sp.points[i].co = (x, y, 0, 1)
        sp.use_cyclic_u = True; sp.use_smooth = True
    ob = bpy.data.objects.new(name, cu); F.link(ob); ob.location.z = z
    return ob

BODY_T = 0.27; BODY_BEV = 0.13
body = curve_obj('body', [outer_px, hole_px], BODY_T - BODY_BEV, BODY_BEV, res=10, z=BODY_T)
mb = F.mat('ivory', F.PAL['ivory'], rough=0.17, coat=0.6, sss=0.1)
F.speckle(mb, 0.01, 170)
F.set_mat(body, mb)

TOP = BODY_T * 2
PUP_T = 0.14; PUP_BEV = 0.05
pupils = []
for i, c in enumerate(CENTERS):
    # corners rounded a little: insert midpoints so the auto bezier keeps the straight sides
    pts = pupil_pts(c)
    dense = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        dense.append(a)
        for t in (0.12, 0.5, 0.88): dense.append([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t])
    pu = curve_obj('pupil%d' % i, [dense], PUP_T - PUP_BEV, PUP_BEV, res=8, z=TOP - 0.22 + PUP_T, round_corners=1)
    F.set_mat(pu, F.mat('pupil', '#1b1940', rough=0.14, coat=0.7))
    pupils.append((pu, c))

cam = F.studio(cam_loc=(-1.7, -3.4, 15.0), cam_target=(0, 0, TOP / 2), lens=85, key=620, fill=190, rim=680, floor=False)

RW, RH = int(1600 * RES), int(1100 * RES)
hull = cv2.convexHull(np.array(outer_px, np.float32).reshape(-1, 1, 2)).reshape(-1, 2).tolist()
meta = {'w': RW, 'h': RH,
        'pupils': [{'center': F.proj((*P(c), TOP)), 'socket': [F.proj((*P(q), TOP)) for q in pupil_pts(c)]} for _, c in pupils],
        'hull': [F.proj((*P(p), TOP)) for p in hull],
        'outline': [F.proj((*P(p), TOP)) for p in outer_px]}

def vis(objs, on):
    for o in objs: o.hide_render = not on

vis([p for p, _ in pupils], False)
F.render(os.path.join(outdir, 'body.png'), RW, RH, SAMPLES)
vis([p for p, _ in pupils], True); body.hide_render = True
F.render(os.path.join(outdir, 'pupils_all.png'), RW, RH, SAMPLES)

# crop each pupil out of the pupil render
im = Image.open(os.path.join(outdir, 'pupils_all.png'))
a = np.array(im)[:, :, 3]
for i, pm in enumerate(meta['pupils']):
    xs = [p[0] * RW for p in pm['socket']]; ys = [p[1] * RH for p in pm['socket']]
    pad = 0.06 * RW
    x0, y0 = int(max(0, min(xs) - pad)), int(max(0, min(ys) - pad)); x1, y1 = int(min(RW, max(xs) + pad)), int(min(RH, max(ys) + pad))
    im.crop((x0, y0, x1, y1)).save(os.path.join(outdir, 'pupil_%s.png' % ('lr'[i])))
    pm['crop'] = [x0 / RW, y0 / RH, (x1 - x0) / RW, (y1 - y0) / RH]
os.remove(os.path.join(outdir, 'pupils_all.png'))
json.dump(meta, open(os.path.join(outdir, 'mascot.json'), 'w'))
print('meta', json.dumps({k: v for k, v in meta.items() if k not in ('outline', 'hull')}))
