"""FOMOINDEX logo in 3D: an ivory rounded tile with the navy fomo mark engraved into it.
usage: python3 -I render_logo.py outdir [samples] [res]"""
import sys, os, json, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, numpy as np
import fomorender as F

outdir = sys.argv[1]; S = int(sys.argv[2]) if len(sys.argv) > 2 else 160; R = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
os.makedirs(outdir, exist_ok=True)
mark = json.load(open('mark.json')); W, H = mark['w'], mark['h']
outer = max(mark['outer'], key=lambda o: o['area']); hole = mark['holes'][0]
bx, by, bw, bh = outer['bbox']
TILE = 4.0; MARKW = TILE * 0.56
Sc = MARKW / (bw * W); cx, cy = (bx + bw / 2) * W, (by + bh / 2) * H
def P(p): return ((p[0] - cx) * Sc, -(p[1] - cy) * Sc)

sc = F.reset()
sc.view_settings.view_transform = 'AgX'; sc.view_settings.look = 'AgX - Medium High Contrast'
sc.world.node_tree.nodes['Background'].inputs[1].default_value = 1.0

# tile: rounded box with a big corner radius, bevelled edges
def rounded_rect(w, r, n=24):
    pts = []
    for cxs, cys, a0 in ((w/2 - r, w/2 - r, 0), (-w/2 + r, w/2 - r, 90), (-w/2 + r, -w/2 + r, 180), (w/2 - r, -w/2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n); pts.append((cxs + r * math.cos(a), cys + r * math.sin(a)))
    return pts
cu = bpy.data.curves.new('tile', 'CURVE'); cu.dimensions = '2D'; cu.fill_mode = 'BOTH'
cu.extrude = 0.22 - 0.07; cu.bevel_depth = 0.07; cu.bevel_resolution = 10; cu.offset = -0.07
sp = cu.splines.new('POLY'); rr = rounded_rect(TILE, TILE * 0.23); sp.points.add(len(rr) - 1)
for i, (x, y) in enumerate(rr): sp.points[i].co = (x, y, 0, 1)
sp.use_cyclic_u = True; sp.use_smooth = True
tile = bpy.data.objects.new('tile', cu); F.link(tile); tile.location.z = 0.0
bpy.ops.object.select_all(action='DESELECT'); tile.select_set(True); bpy.context.view_layer.objects.active = tile
bpy.ops.object.convert(target='MESH'); tile = bpy.context.active_object
mt = F.mat('ivory', F.PAL['ivory'], rough=0.2, coat=0.5, sss=0.08); F.speckle(mt, 0.01, 200)
F.set_mat(tile, mt)

# the mark, engraved: a navy inlay sitting in a shallow recess
def curve_obj(name, loops, extrude, bevel, z, res=8):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '2D'; cu.fill_mode = 'BOTH'
    cu.extrude = extrude; cu.bevel_depth = bevel; cu.bevel_resolution = res; cu.resolution_u = 6; cu.offset = -bevel
    for pts in loops:
        sp = cu.splines.new('POLY'); sp.points.add(len(pts) - 1)
        for i, p in enumerate(pts):
            x, y = P(p); sp.points[i].co = (x, y, 0, 1)
        sp.use_cyclic_u = True; sp.use_smooth = True
    ob = bpy.data.objects.new(name, cu); F.link(ob); ob.location.z = z; return ob
outer_px = [[p[0] * W, p[1] * H] for p in outer['pts']]; hole_px = [[p[0] * W, p[1] * H] for p in hole['pts']]
# recess: boolean-cut the mark 0.06 deep into the tile top
cutter = curve_obj('cutter', [outer_px, hole_px], 0.08, 0.0, 0.22)
bpy.context.view_layer.update()
bpy.ops.object.select_all(action='DESELECT'); cutter.select_set(True); bpy.context.view_layer.objects.active = cutter
bpy.ops.object.convert(target='MESH')
cutter = bpy.context.active_object
bo = tile.modifiers.new('cut', 'BOOLEAN'); bo.operation = 'DIFFERENCE'; bo.object = cutter; bo.solver = 'EXACT'
cutter.hide_render = True
# inlay: navy glossy piece filling the recess, top face 0.01 below the tile face
inlay = curve_obj('inlay', [outer_px, hole_px], 0.03, 0.012, 0.22 - 0.06 + 0.03 - 0.005)
F.set_mat(inlay, F.mat('navy', '#0b0a1f', rough=0.38, coat=0.15))

TOP = 0.22
cam = F.studio(cam_loc=(-1.2, -5.2, 9.5), cam_target=(0, 0, 0.1), lens=70, key=700, fill=220, rim=600, floor=False)
RW, RH = int(1400 * R), int(1400 * R)
F.render(os.path.join(outdir, 'logo3d.png'), RW, RH, S)
# straight-on version for the og image and favicon-sized uses
cam.location = (0, -0.4, 11.0); F.look_down(cam, (0, 0, 0.1))
F.render(os.path.join(outdir, 'logo3d-front.png'), RW, RH, S)
