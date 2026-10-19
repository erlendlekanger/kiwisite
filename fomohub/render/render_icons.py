"""Six 3D icons for FOMOHUB. usage: python3 -I render_icons.py outdir [samples] [name,name...]"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy, bmesh
from mathutils import Vector, Matrix
import fomorender as F

outdir = sys.argv[1]; SAMPLES = int(sys.argv[2]) if len(sys.argv) > 2 else 160
ONLY = sys.argv[3].split(',') if len(sys.argv) > 3 else None
os.makedirs(outdir, exist_ok=True)
P = F.PAL

def lathe(name, profile, segs=96, loc=(0, 0, 0), close_top=True, close_bottom=True):
    """profile: list of (r, z) from bottom to top, revolved around Z."""
    bm = bmesh.new(); rings = []
    for (r, z) in profile:
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for a, b in zip(rings, rings[1:]):
        for i in range(segs):
            v1, v2, v3, v4 = a[i], a[(i + 1) % segs], b[(i + 1) % segs], b[i]
            if v1.co != v4.co and v2.co != v3.co:
                bm.faces.new((v1, v2, v3, v4))
    if close_bottom and profile[0][0] > 0: bm.faces.new(reversed(rings[0]))
    if close_top and profile[-1][0] > 0: bm.faces.new(rings[-1])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); F.link(ob); ob.location = loc
    for p in me.polygons: p.use_smooth = True
    return ob

def rounded_box(name, size, r=0.06, loc=(0, 0, 0), rot=(0, 0, 0), segs=6):
    ob = F.prim('cube', name, loc=loc, rot=rot, scale=(size[0] / 2, size[1] / 2, size[2] / 2))
    bpy.ops.object.transform_apply(scale=True)
    F.add_mod_bevel(ob, min(r, min(size) / 2.2), segs)
    for p in ob.data.polygons: p.use_smooth = False
    return ob

def text(name, body, size=0.5, extrude=0.03, loc=(0, 0, 0), rot=(0, 0, 0)):
    cu = bpy.data.curves.new(name, 'FONT'); cu.body = body; cu.size = size; cu.extrude = extrude
    cu.align_x = 'CENTER'; cu.align_y = 'CENTER'; cu.bevel_depth = 0.006; cu.bevel_resolution = 2
    ob = bpy.data.objects.new(name, cu); F.link(ob); ob.location = loc; ob.rotation_euler = rot
    return ob

def coin(name, loc, rot=(0, 0, 0), r=0.34, t=0.07, m=None):
    c = F.prim('cyl', name, loc=loc, rot=rot, radius=r, depth=t, vertices=96)
    F.add_mod_bevel(c, t * 0.35, 4); F.smooth(c, 40); F.set_mat(c, m)
    # a ring groove on the faces, like a real coin
    ring = F.prim('torus', name + '_ring', loc=(loc[0], loc[1], loc[2]), rot=rot, major_radius=r * 0.74, minor_radius=t * 0.16, major_segments=96, minor_segments=12)
    ring.parent = c; ring.matrix_parent_inverse = c.matrix_world.inverted()
    ring.location = (0, 0, t / 2); F.set_mat(ring, F.mat('ring', P['ivory'], 0.3, 0.2))
    ring2 = F.prim('torus', name + '_ring2', loc=loc, rot=rot, major_radius=r * 0.74, minor_radius=t * 0.16, major_segments=96, minor_segments=12)
    ring2.parent = c; ring2.matrix_parent_inverse = c.matrix_world.inverted(); ring2.location = (0, 0, -t / 2)
    F.set_mat(ring2, ring.data.materials[0])
    return c

GOLD = lambda: F.mat('gold', P['gold'], rough=0.28, metal=1.0, coat=0.0)
BLUE = lambda: F.mat('blue', P['blue'], rough=0.3, coat=0.35)
NAVY = lambda: F.mat('navy', P['navy'], rough=0.2, coat=0.5)
IVORY = lambda: F.mat('ivory', P['ivory'], rough=0.25, coat=0.3, sss=0.08)
ORANGE = lambda: F.mat('orange', P['orange'], rough=0.3, coat=0.35)

# ---------------------------------------------------------------- FOMOSPEND: gift card + coins
def spend():
    e = bpy.data.objects.new('cardroot', None); F.link(e)
    card = rounded_box('card', (2.0, 1.26, 0.08), r=0.1); F.set_mat(card, BLUE()); card.parent = e
    band = rounded_box('band', (2.0, 0.26, 0.03), r=0.01, loc=(0, -0.3, 0.05)); band.parent = e; F.set_mat(band, IVORY())
    chip = rounded_box('chip', (0.36, 0.28, 0.04), r=0.04, loc=(-0.62, 0.3, 0.05)); chip.parent = e; F.set_mat(chip, GOLD())
    for i in range(3):
        g = rounded_box('groove%d' % i, (0.3, 0.012, 0.045), r=0.004, loc=(-0.62, 0.3 - 0.07 + 0.07 * i, 0.05)); g.parent = e; F.set_mat(g, NAVY())
    for dx in (0.36, 0.68):
        eye = F.prim('sphere', 'eye', loc=(dx, 0.3, 0.04), radius=0.13, segments=48, ring_count=24); eye.scale = (1, 1, 0.45); eye.parent = e; F.set_mat(eye, IVORY())
        pu = F.prim('sphere', 'pupil', loc=(dx + 0.03, 0.29, 0.09), radius=0.055, segments=32, ring_count=16); pu.scale = (1, 1, 0.5); pu.parent = e; F.set_mat(pu, NAVY())
    # a short line of embossed digits like a card number
    for i in range(4):
        d = rounded_box('digit%d' % i, (0.3, 0.07, 0.03), r=0.01, loc=(-0.62 + i * 0.42, -0.3, 0.06)); d.parent = e; F.set_mat(d, F.mat('emb', P['blue'], 0.3, 0.3))
    e.location = (-0.2, 0.15, 0.72); e.rotation_euler = (math.radians(68), 0, math.radians(-16))
    g = GOLD()
    coin('c1', (0.95, -0.6, 0.035), m=g); coin('c2', (0.98, -0.55, 0.105), rot=(0, 0, 0.4), m=g)
    coin('c3', (0.92, -0.63, 0.175), rot=(0, 0, 0.9), m=g)
    coin('c4', (-1.15, -0.85, 0.34), rot=(math.radians(80), 0, math.radians(35)), m=g)
    F.studio(cam_loc=(0.6, -6.4, 3.1), cam_target=(0, 0, 0.6), lens=75, fill=500)

# ---------------------------------------------------------------- LEADERBOARD: podium
def leaderboard():
    blue, navy, ivory = BLUE(), NAVY(), IVORY()
    tops = {'1': (0, 1.5, GOLD()), '2': (-1.1, 1.05, F.mat('silver', P['silver'], 0.35, 0.2, metal=0.9)), '3': (1.1, 0.75, F.mat('bronze', P['bronze'], 0.35, 0.1, metal=0.9))}
    for n, (x, h, m) in tops.items():
        b = rounded_box('block' + n, (1.06, 1.0, h), r=0.05, loc=(x, 0, h / 2)); F.set_mat(b, blue)
        cap = rounded_box('cap' + n, (1.06, 1.0, 0.1), r=0.04, loc=(x, 0, h + 0.05)); F.set_mat(cap, m)
        t = text('t' + n, n, size=0.56, extrude=0.03, loc=(x, -0.5, h / 2), rot=(math.radians(90), 0, 0)); F.set_mat(t, ivory)
    # little star on top of #1
    star = text('star', '★', size=0.5, extrude=0.08, loc=(0, 0, 1.85), rot=(math.radians(90), 0, 0)); F.set_mat(star, GOLD())
    F.studio(cam_loc=(0.9, -6.6, 3.0), cam_target=(0, 0, 0.95), lens=70, fill=500)

# ---------------------------------------------------------------- FOMOFANTASY: trophy
def fantasy():
    gold, navy = GOLD(), NAVY()
    base = lathe('base', [(0.0, 0), (0.95, 0), (0.95, 0.22), (0.8, 0.26), (0.8, 0.5), (0.0, 0.5)], loc=(0, 0, 0)); F.set_mat(base, navy); F.smooth(base, 35)
    stem = lathe('stem', [(0, 0.5), (0.5, 0.5), (0.5, 0.58), (0.16, 0.7), (0.14, 1.0), (0.3, 1.15), (0.0, 1.15)]); F.set_mat(stem, gold); F.smooth(stem, 35)
    cup = lathe('cup', [(0.0, 1.1), (0.34, 1.1), (0.62, 1.4), (0.78, 1.9), (0.86, 2.4), (0.95, 2.55), (0.9, 2.56), (0.8, 2.42), (0.72, 1.95), (0.56, 1.45), (0.3, 1.2), (0.0, 1.2)])
    F.set_mat(cup, gold); F.smooth(cup, 35)
    for s in (1, -1):
        h = F.prim('torus', 'handle', loc=(s * 0.98, 0, 2.0), rot=(math.radians(90), 0, 0), major_radius=0.38, minor_radius=0.07, major_segments=64, minor_segments=24)
        h.scale = (1, 1.25, 1); F.set_mat(h, gold)
    plate = rounded_box('plate', (0.7, 0.05, 0.26), r=0.02, loc=(0, -0.82, 0.3)); F.set_mat(plate, gold)
    # two eyes on the cup, the fomo mark
    for dx in (-0.22, 0.22):
        e = F.prim('sphere', 'eye', loc=(dx, -0.72, 1.95), radius=0.14, segments=48, ring_count=24); e.scale = (1, 0.5, 1); F.set_mat(e, IVORY())
        pu = F.prim('sphere', 'pupil', loc=(dx + 0.03, -0.78, 1.95), radius=0.06, segments=32, ring_count=16); pu.scale = (1, 0.5, 1); F.set_mat(pu, navy)
    F.studio(cam_loc=(0.8, -7.0, 3.3), cam_target=(0, 0, 1.3), lens=70, fill=500)

# ---------------------------------------------------------------- FOMOPREDICT: crystal ball
def predict():
    sc = bpy.context.scene; sc.cycles.film_transparent_glass = True; sc.cycles.film_transparent_roughness = 0.1
    stand = lathe('stand', [(0, 0), (0.95, 0), (0.95, 0.18), (0.75, 0.26), (0.62, 0.55), (0.78, 0.7), (0.66, 0.76), (0.0, 0.76)]); F.set_mat(stand, NAVY()); F.smooth(stand, 35)
    ring = F.prim('torus', 'ring', loc=(0, 0, 0.72), major_radius=0.7, minor_radius=0.06, major_segments=96, minor_segments=24); F.set_mat(ring, GOLD())
    ball = F.prim('sphere', 'ball', loc=(0, 0, 1.55), radius=0.95, segments=96, ring_count=48)
    F.set_mat(ball, F.mat('glass', (1, 1, 1, 1), rough=0.02, coat=0.0, trans=1.0, ior=1.47))
    core = F.prim('sphere', 'core', loc=(0, 0, 1.5), radius=0.3, segments=64, ring_count=32)
    mc = F.mat('core', P['violet'], rough=0.6, coat=0, emit=P['violet']); F.set_mat(core, mc)
    # swirling wisps inside: a few small glowing spheres
    for i, (x, y, z, r) in enumerate([(0.25, -0.2, 1.85, 0.08), (-0.3, 0.1, 1.3, 0.1), (0.1, 0.3, 1.95, 0.06), (-0.15, -0.3, 1.65, 0.05)]):
        w = F.prim('sphere', 'w%d' % i, loc=(x, y, z), radius=r, segments=32, ring_count=16)
        F.set_mat(w, F.mat('wisp', P['ivory'], rough=0.5, coat=0, emit=P['ivory']))
    F.studio(cam_loc=(0.6, -6.8, 2.6), cam_target=(0, 0, 1.2), lens=72, key=1500, fill=500, rim=800)

# ---------------------------------------------------------------- FOMOQUESTS: treasure chest
def quests():
    blue, navy, gold = BLUE(), NAVY(), GOLD()
    base = rounded_box('base', (2.0, 1.3, 0.95), r=0.05, loc=(0, 0, 0.475)); F.set_mat(base, blue)
    # gold bands around the base
    for x in (-0.68, 0.68):
        b = rounded_box('band', (0.16, 1.34, 0.98), r=0.02, loc=(x, 0, 0.49)); F.set_mat(b, gold)
    rim = rounded_box('rim', (2.04, 1.34, 0.08), r=0.02, loc=(0, 0, 0.95)); F.set_mat(rim, gold)
    # lid: half cylinder hinged at the back, opened
    lid = F.prim('cyl', 'lid', loc=(0, 0, 0), rot=(0, math.radians(90), 0), radius=0.65, depth=2.0, vertices=64)
    bpy.ops.object.transform_apply(rotation=True)
    bm = bmesh.new(); bm.from_mesh(lid.data)
    for v in list(bm.verts):
        if v.co.z < -0.001: bm.verts.remove(v)
    bm.to_mesh(lid.data); bm.free()
    # fill the flat underside
    bpy.context.view_layer.objects.active = lid; lid.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT'); bpy.ops.mesh.edge_face_add(); bpy.ops.object.mode_set(mode='OBJECT'); lid.select_set(False)
    sol = lid.modifiers.new('solid', 'SOLIDIFY'); sol.thickness = 0.08; sol.offset = -1
    F.smooth(lid, 30); F.set_mat(lid, blue)
    lid.location = (0, 0.65, 0.99); lid.rotation_euler = (math.radians(-38), 0, 0)
    for x in (-0.68, 0.68):
        lb = F.prim('torus', 'lband', loc=(0, 0, 0), rot=(0, math.radians(90), 0), major_radius=0.68, minor_radius=0.05, major_segments=64, minor_segments=16)
        lb.parent = lid; lb.location = (x, 0, 0); F.set_mat(lb, gold)
    lb2 = F.prim('cyl', 'lband2', loc=(0, 0, 0), rot=(0, math.radians(90), 0), radius=0.7, depth=2.04, vertices=64); lb2.parent = lid
    bm2 = bmesh.new(); bm2.from_mesh(lb2.data)
    for v in list(bm2.verts):
        if v.co.z < 0.28: bm2.verts.remove(v)
    bm2.to_mesh(lb2.data); bm2.free(); F.smooth(lb2, 30); F.set_mat(lb2, gold)
    sol2 = lb2.modifiers.new('solid', 'SOLIDIFY'); sol2.thickness = 0.05; sol2.offset = 1
    lock = rounded_box('lock', (0.34, 0.1, 0.4), r=0.04, loc=(0, -0.68, 0.72)); F.set_mat(lock, gold)
    key = F.prim('cyl', 'keyhole', loc=(0, -0.74, 0.76), rot=(math.radians(90), 0, 0), radius=0.06, depth=0.04, vertices=32); F.set_mat(key, navy)
    # coins piled inside and spilling out
    import random; random.seed(7)
    for i in range(14):
        x = random.uniform(-0.75, 0.75); y = random.uniform(-0.55, -0.2); z = 0.9 + random.uniform(0, 0.2)
        coin('coin%d' % i, (x, y, z), rot=(random.uniform(-0.4, 0.4), random.uniform(-0.4, 0.4), random.uniform(0, 3)), r=0.22, t=0.05, m=gold)
    coin('cs1', (1.25, -0.5, 0.025), r=0.22, t=0.05, m=gold); coin('cs2', (1.35, -0.3, 0.075), rot=(0, 0, 1), r=0.22, t=0.05, m=gold)
    coin('cs3', (-1.3, -0.4, 0.22), rot=(math.radians(80), 0, 0.5), r=0.22, t=0.05, m=gold)
    F.studio(cam_loc=(1.0, -6.6, 3.2), cam_target=(0, 0, 0.75), lens=70, fill=500)

# ---------------------------------------------------------------- FOMORADAR: satellite dish
def radar():
    blue, navy, ivory = BLUE(), NAVY(), IVORY()
    base = lathe('base', [(0, 0), (0.9, 0), (0.9, 0.16), (0.7, 0.2), (0.0, 0.2)]); F.set_mat(base, navy); F.smooth(base, 35)
    post = F.prim('cyl', 'post', loc=(0, 0, 0.75), radius=0.11, depth=1.2, vertices=48); F.set_mat(post, navy)
    joint = F.prim('sphere', 'joint', loc=(0, 0, 1.35), radius=0.2, segments=48, ring_count=24); F.set_mat(joint, blue)
    # paraboloid dish (profile r, z=k r^2) with a thickness
    k = 0.95; prof = [(r, k * r * r) for r in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.15]]
    outer = [(r + 0.05, z - 0.05) for (r, z) in prof]
    dish = lathe('dish', [(0, -0.05)] + outer[1:] + [(1.2, k * 1.15 ** 2 + 0.02)] + list(reversed(prof)), segs=128)
    F.set_mat(dish, F.mat('dish', P['silver'], rough=0.38, coat=0.2)); F.smooth(dish, 35)
    lip = F.prim('torus', 'lip', loc=(0, 0, k * 1.15 ** 2), major_radius=1.17, minor_radius=0.05, major_segments=128, minor_segments=16); lip.parent = dish; F.set_mat(lip, blue)
    dish.location = (0, 0, 1.55); dish.rotation_euler = (math.radians(42), 0, math.radians(-22))
    # feed arm + receiver
    arm = F.prim('cyl', 'arm', loc=(0, 0, 0.5), radius=0.035, depth=1.0, vertices=24); arm.parent = dish; F.set_mat(arm, navy)
    rec = F.prim('sphere', 'rec', loc=(0, 0, 1.0), radius=0.12, segments=48, ring_count=24); rec.parent = dish; F.set_mat(rec, blue)
    hub = F.prim('sphere', 'hub', loc=(0, 0, 0.02), radius=0.16, segments=48, ring_count=24); hub.parent = dish; F.set_mat(hub, blue)
    # signal rings leaving the dish
    for i, r in enumerate((0.16, 0.26, 0.36)):
        ring = F.prim('torus', 'sig%d' % i, loc=(0, 0, 1.3 + i * 0.32), major_radius=r, minor_radius=0.025, major_segments=96, minor_segments=16)
        ring.parent = dish; F.set_mat(ring, F.mat('sig', P['orange'], 0.4, 0.2, emit=P['orange']))
    F.studio(cam_loc=(0.8, -7.4, 3.6), cam_target=(0, 0, 1.45), lens=65, key=900, fill=450)

ICONS = {'spend': spend, 'leaderboard': leaderboard, 'fantasy': fantasy, 'predict': predict, 'quests': quests, 'radar': radar}
for name, build in ICONS.items():
    if ONLY and name not in ONLY: continue
    F.reset(); build()
    F.render(os.path.join(outdir, name + '.png'), 900, 900, SAMPLES)
