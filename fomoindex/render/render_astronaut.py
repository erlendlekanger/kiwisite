"""FOMOINDEX hero: astronaut floating in space, reaching toward the camera with an iPhone.

Usage:  python3 -I render_astronaut.py test|hd|4k [out.png]
Everything is procedural (bpy 5.x, CPU Cycles). Needs fomorender.py and screen.png next to this file.
"""
import sys, os, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                     # python -I does not add the script dir
import bpy, bmesh
from mathutils import Vector, Matrix, Euler
import fomorender as F

MODE = sys.argv[1] if len(sys.argv) > 1 else 'test'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, f'astro_{MODE}.png')
SCREEN_PNG = os.path.join(HERE, 'screen.png')

NAVY, IVORY, BLUE, GREEN, GOLD = '#060510', '#EAEDFF', '#516af6', '#21c95e', '#d9a53a'

# ------------------------------------------------------------------ scene
sc = F.reset()
sc.view_settings.view_transform = 'AgX'
sc.view_settings.look = 'AgX - Punchy'
sc.cycles.max_bounces = 10
# world: very dark navy gradient (lives in reflections only; film is transparent)
wnt = sc.world.node_tree
ramp = [n for n in wnt.nodes if n.type == 'VALTORGB'][0]
ramp.color_ramp.elements[0].color = (0.002, 0.002, 0.008, 1)
ramp.color_ramp.elements[1].color = (0.03, 0.045, 0.16, 1)
wnt.nodes['Background'].inputs[1].default_value = 0.6

# ------------------------------------------------------------------ materials
def principled(m):
    return m.node_tree.nodes['Principled BSDF']

M_SUIT = F.mat('suit', '#f2f2f0', rough=0.65, coat=0.0, spec=0.45)
p = principled(M_SUIT)
p.inputs['Sheen Weight'].default_value = 0.4
p.inputs['Sheen Roughness'].default_value = 0.45
F.speckle(M_SUIT, strength=0.18, scale=260)          # fine fabric weave bump

M_NAVY = F.mat('navy', NAVY, rough=0.45, coat=0.15)
M_BLUE = F.mat('blue', BLUE, rough=0.5, coat=0.1)
M_GREY = F.mat('grey', '#8b8d96', rough=0.5, coat=0.0, metal=0.3)
M_RING = F.mat('ring', '#9a9ca6', rough=0.35, coat=0.0, metal=0.85)
M_GOLD = F.mat('gold', GOLD, rough=0.1, coat=0.0, metal=1.0)
M_TITAN = F.mat('titanium', '#7a7a80', rough=0.3, coat=0.0, metal=0.9)
M_BLACK = F.mat('black', '#0a0a0c', rough=0.2, coat=0.5)
M_HOSE = F.mat('hose', '#2b2b33', rough=0.55, coat=0.0)
F.speckle(M_HOSE, strength=0.3, scale=40)
M_LED_B = F.mat('ledb', BLUE, rough=0.3, emit=BLUE); principled(M_LED_B).inputs['Emission Strength'].default_value = 6
M_LED_G = F.mat('ledg', GREEN, rough=0.3, emit=GREEN); principled(M_LED_G).inputs['Emission Strength'].default_value = 6
M_LAMP = F.mat('lamp', '#ffffff', rough=0.2, emit='#fff6e8'); principled(M_LAMP).inputs['Emission Strength'].default_value = 8

def screen_mat():
    m = bpy.data.materials.new('screen'); m.use_nodes = True
    nt = m.node_tree; p = nt.nodes['Principled BSDF']
    img = bpy.data.images.load(SCREEN_PNG)
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img; tex.extension = 'EXTEND'
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ'); comb = nt.nodes.new('ShaderNodeCombineXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    nt.links.new(sep.outputs['X'], comb.inputs['X']); nt.links.new(sep.outputs['Z'], comb.inputs['Y'])   # slab lies in XZ
    nt.links.new(comb.outputs[0], tex.inputs['Vector'])
    nt.links.new(tex.outputs['Color'], p.inputs['Base Color'])
    nt.links.new(tex.outputs['Color'], p.inputs['Emission Color'])
    p.inputs['Emission Strength'].default_value = 2.5
    p.inputs['Roughness'].default_value = 0.15
    p.inputs['Specular IOR Level'].default_value = 0.4
    p.inputs['Coat Weight'].default_value = 0.8          # slight glass coat
    p.inputs['Coat Roughness'].default_value = 0.03
    return m
M_SCREEN = screen_mat()

# ------------------------------------------------------------------ helpers
def smooth_all():
    for ob in bpy.data.objects:
        if ob.type == 'MESH':
            F.smooth(ob, 45)

def frame(origin, z_axis, up_hint=(0, 0, 1)):
    """4x4 matrix whose local Z points along z_axis, local Y as close to up_hint as possible."""
    z = Vector(z_axis).normalized()
    y = Vector(up_hint)
    if abs(y.dot(z)) > 0.98: y = Vector((0, -1, 0))
    x = y.cross(z).normalized(); y = z.cross(x).normalized()
    m = Matrix((x, y, z)).transposed().to_4x4(); m.translation = Vector(origin)
    return m

def rounded_box(name, center, half, bevel, m, parent=None, segs=6, matrix=None):
    ob = F.prim('cube', name, loc=center, scale=half)
    bpy.ops.object.transform_apply(scale=True)
    b = F.add_mod_bevel(ob, width=bevel, segments=segs); b.limit_method = 'NONE'
    F.set_mat(ob, m)
    if matrix is not None: ob.matrix_world = matrix @ Matrix.Translation(center)
    if parent: ob.parent = parent
    return ob

def capsule(name, a, b, r1, r2, m, parent=None):
    a, b = Vector(a), Vector(b); d = b - a
    ob = F.prim('cone', name, loc=(a + b) / 2, radius1=r1, radius2=r2, depth=d.length, vertices=40)
    ob.rotation_euler = d.to_track_quat('Z', 'Y').to_euler()
    F.set_mat(ob, m)
    s1 = F.prim('sphere', name + '_a', loc=a, radius=r1, segments=40, ring_count=24); F.set_mat(s1, m)
    s2 = F.prim('sphere', name + '_b', loc=b, radius=r2, segments=40, ring_count=24); F.set_mat(s2, m)
    for o in (ob, s1, s2):
        if parent: o.parent = parent
    return [ob, s1, s2]

def rings(name, p, direction, r, m=M_RING, n=3, spacing=0.03, minor=0.011, parent=None):
    d = Vector(direction).normalized()
    out = []
    for i in range(n):
        c = Vector(p) + d * ((i - (n - 1) / 2) * spacing)
        t = F.prim('torus', f'{name}{i}', loc=c, major_radius=r, minor_radius=minor, major_segments=48, minor_segments=14)
        t.rotation_euler = d.to_track_quat('Z', 'Y').to_euler(); F.set_mat(t, m)
        if parent: t.parent = parent
        out.append(t)
    return out

def band(name, p, direction, r, m, width=0.02, parent=None):
    """thin stripe around a limb"""
    t = F.prim('cyl', name, loc=p, radius=r, depth=width, vertices=48)
    t.rotation_euler = Vector(direction).to_track_quat('Z', 'Y').to_euler(); F.set_mat(t, m)
    if parent: t.parent = parent
    return t

def hose(name, pts, radius, m, parent=None):
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'
    cu.bevel_depth = radius; cu.bevel_resolution = 6; cu.resolution_u = 24
    sp = cu.splines.new('BEZIER'); sp.bezier_points.add(len(pts) - 1)
    for bp, pt in zip(sp.bezier_points, pts):
        bp.co = Vector(pt); bp.handle_left_type = bp.handle_right_type = 'AUTO'
    ob = bpy.data.objects.new(name, cu); F.link(ob); ob.data.materials.append(m)
    if parent: ob.parent = parent
    return ob

# ------------------------------------------------------------------ iPhone
PS = 2.2                                   # phone scale (hero cheat: reads big in the glove)
PW, PH, PT, PR = 0.0716 * PS, 0.1466 * PS, 0.00825 * PS, 0.012 * PS

def rrect_verts(w, h, r, n=10, z=0.0):
    pts = []
    for cx, cy, a0 in ((w/2 - r, h/2 - r, 0), (-w/2 + r, h/2 - r, 90), (-w/2 + r, -h/2 + r, 180), (w/2 - r, -h/2 + r, 270)):
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    return pts

def rrect_slab(name, w, h, r, t, m, rim_bevel=0.0):
    """rounded-rectangle slab lying in XZ, thickness along Y (front = -Y)."""
    bm = bmesh.new()
    vs = [bm.verts.new((x, -t / 2, y)) for x, y, _ in rrect_verts(w, h, r)]
    f = bm.faces.new(vs)
    bm.normal_update()
    if f.normal.y > 0: bmesh.ops.reverse_faces(bm, faces=[f])
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    verts = [g for g in ext['geom'] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, verts=verts, vec=(0, t, 0))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); F.link(ob); ob.data.materials.append(m)
    if rim_bevel:
        b = ob.modifiers.new('bevel', 'BEVEL'); b.width = rim_bevel; b.segments = 4
        b.limit_method = 'ANGLE'; b.angle_limit = math.radians(60)
    return ob

def build_phone(mat_world):
    parts = []
    body = rrect_slab('phone_body', PW, PH, PR, PT, M_TITAN, rim_bevel=0.0016 * PS)
    parts.append(body)
    # front glass (black bezel plate) slightly proud of the frame
    glass = rrect_slab('phone_glass', PW - 0.0015 * PS, PH - 0.0015 * PS, PR - 0.0008 * PS, 0.0012 * PS, M_BLACK)
    glass.location.y = -PT / 2 - 0.0004 * PS; parts.append(glass)
    # screen: emissive rounded rect, inset bezel ~2.2 mm
    bz = 0.0022 * PS
    scr = rrect_slab('phone_screen', PW - 2 * bz, PH - 2 * bz, PR - bz, 0.0006 * PS, M_SCREEN)
    scr.location.y = -PT / 2 - 0.0012 * PS; parts.append(scr)
    # dynamic island
    di = rrect_slab('island', 0.0255 * PS, 0.0075 * PS, 0.0037 * PS, 0.0005 * PS, M_BLACK)
    di.location = (0, -PT / 2 - 0.0017 * PS, PH / 2 - 0.0085 * PS); parts.append(di)
    # side buttons + action button on the frame
    for z, h, side in ((0.032 * PS, 0.011 * PS, 1), (0.018 * PS, 0.022 * PS, -1), (-0.008 * PS, 0.022 * PS, -1), (0.040 * PS, 0.007 * PS, -1)):
        b = F.prim('cube', 'btn', loc=(side * (PW / 2 + 0.0004 * PS), 0, z), scale=(0.0008 * PS, 0.0022 * PS, h / 2))
        F.set_mat(b, M_TITAN); parts.append(b)
    # back camera bump (mostly hidden, but catches the rim)
    cam = rrect_slab('cambump', 0.034 * PS, 0.036 * PS, 0.008 * PS, 0.002 * PS, M_TITAN)
    cam.location = (-PW / 2 + 0.021 * PS, PT / 2 + 0.001 * PS, PH / 2 - 0.022 * PS); parts.append(cam)
    for (dx, dz) in ((-0.008, 0.008), (-0.008, -0.008), (0.008, 0.0)):
        l = F.prim('cyl', 'lens', loc=(-PW / 2 + 0.021 * PS + dx * PS, PT / 2 + 0.0035 * PS, PH / 2 - 0.022 * PS + dz * PS),
                   rot=(math.pi / 2, 0, 0), radius=0.0055 * PS, depth=0.003 * PS, vertices=32)
        F.set_mat(l, M_BLACK); parts.append(l)
    bpy.context.view_layer.update()            # location/rotation set above are not in matrix_world yet
    for o in parts:
        o.matrix_world = mat_world @ o.matrix_world
    return parts

# ------------------------------------------------------------------ astronaut (body space: up +Z, facing -Y, right side -X)
root = bpy.data.objects.new('ROOT', None); F.link(root)
PITCH, ROLL, YAW = math.radians(22), math.radians(38), math.radians(28)
ROOT_M = Matrix.Translation((-0.3, 0.1, 0.12)) @ Euler((PITCH, ROLL, YAW), 'XYZ').to_matrix().to_4x4()
root.matrix_world = ROOT_M

def body(ob):
    ob.parent = root; return ob

# torso
rounded_box('hut', (0, 0.0, 1.13), (0.27, 0.17, 0.2), 0.1, M_SUIT, parent=root, segs=8)
rounded_box('belly', (0, 0.0, 0.82), (0.225, 0.155, 0.19), 0.09, M_SUIT, parent=root, segs=8)
rounded_box('hips', (0, 0.0, 0.66), (0.24, 0.165, 0.09), 0.07, M_SUIT, parent=root, segs=6)
rounded_box('waist_belt', (0, 0.0, 0.70), (0.245, 0.17, 0.02), 0.015, M_NAVY, parent=root, segs=3)
# chest stripe + control panel
rounded_box('chest_stripe', (0, -0.172, 1.235), (0.17, 0.004, 0.012), 0.003, M_BLUE, parent=root, segs=2)
rounded_box('panel', (0, -0.18, 1.09), (0.12, 0.028, 0.075), 0.012, M_NAVY, parent=root, segs=4)
rounded_box('panel_face', (0, -0.208, 1.09), (0.1, 0.002, 0.055), 0.004, M_BLACK, parent=root, segs=2)
for i, (x, mm) in enumerate(((-0.075, M_LED_B), (-0.045, M_LED_G), (-0.015, M_LED_G))):
    rounded_box(f'led{i}', (x, -0.211, 1.125), (0.01, 0.002, 0.006), 0.002, mm, parent=root, segs=2)
for x in (0.045, 0.08):
    k = F.prim('cyl', 'knob', loc=(x, -0.218, 1.075), rot=(math.pi / 2, 0, 0), radius=0.014, depth=0.02, vertices=32)
    F.set_mat(k, M_GREY); body(k)
# shoulders
for sx in (-1, 1):
    s = F.prim('sphere', 'shoulder', loc=(sx * 0.3, 0.0, 1.27), radius=0.105, segments=48, ring_count=24); F.set_mat(s, M_SUIT); body(s)
    rings('shring', (sx * 0.33, 0.0, 1.27), (sx, 0, 0), 0.1, n=2, spacing=0.035, parent=root)
# neck ring + helmet
HEAD = Vector((0, -0.01, 1.60)); HR = 0.215
nr = F.prim('torus', 'neckring', loc=(0, -0.01, 1.4), major_radius=0.135, minor_radius=0.03, major_segments=64, minor_segments=16)
F.set_mat(nr, M_RING); body(nr)
nc = F.prim('cyl', 'neck', loc=(0, -0.01, 1.42), radius=0.13, depth=0.08, vertices=48); F.set_mat(nc, M_NAVY); body(nc)

def helmet_shell():
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=HR)
    cut = HR * math.cos(math.radians(63))
    kill = [f for f in bm.faces if f.calc_center_median().z > cut]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    me = bpy.data.meshes.new('helmet'); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new('helmet', me); F.link(ob); ob.data.materials.append(M_SUIT)
    so = ob.modifiers.new('solid', 'SOLIDIFY'); so.thickness = 0.014; so.offset = -1; so.use_rim = True
    ob.location = HEAD; ob.rotation_euler = (math.pi / 2, 0, 0)        # pole -> -Y (front)
    return ob
body(helmet_shell())
vis = F.prim('sphere', 'visor', loc=HEAD + Vector((0, 0.005, 0)), radius=HR - 0.016, segments=96, ring_count=48)
F.set_mat(vis, M_GOLD); body(vis)
# visor rim ring at the opening edge
ang = math.radians(63)
vr = F.prim('torus', 'visor_rim', loc=HEAD + Vector((0, -HR * math.cos(ang), 0)), rot=(math.pi / 2, 0, 0),
            major_radius=HR * math.sin(ang), minor_radius=0.012, major_segments=96, minor_segments=16)
F.set_mat(vr, M_RING); body(vr)
# helmet lights + cam block on top
for sx in (-1, 1):
    lb = rounded_box('hlamp', HEAD + Vector((sx * 0.19, -0.07, 0.11)), (0.025, 0.035, 0.022), 0.01, M_SUIT, parent=root, segs=3)
    lens = F.prim('cyl', 'hlens', loc=HEAD + Vector((sx * 0.19, -0.108, 0.11)), rot=(math.pi / 2, 0, 0), radius=0.016, depth=0.006, vertices=32)
    F.set_mat(lens, M_LAMP); body(lens)
rounded_box('hcam', HEAD + Vector((0, 0.02, 0.21)), (0.04, 0.05, 0.02), 0.012, M_NAVY, parent=root, segs=3)

# backpack (PLSS)
rounded_box('plss', (0, 0.31, 1.02), (0.245, 0.13, 0.34), 0.05, M_SUIT, parent=root, segs=6)
rounded_box('plss_top', (0, 0.31, 1.37), (0.17, 0.1, 0.03), 0.02, M_NAVY, parent=root, segs=3)
rounded_box('plss_stripe', (0, 0.31, 0.72), (0.25, 0.135, 0.012), 0.005, M_BLUE, parent=root, segs=2)
for sx in (-1, 1):
    t = F.prim('cyl', 'tank', loc=(sx * 0.12, 0.33, 1.47), radius=0.045, depth=0.14, vertices=40); F.set_mat(t, M_GREY); body(t)
    tc = F.prim('sphere', 'tankcap', loc=(sx * 0.12, 0.33, 1.54), radius=0.045, segments=40, ring_count=20); F.set_mat(tc, M_GREY); body(tc)
ant = F.prim('cyl', 'antenna', loc=(0.2, 0.36, 1.55), radius=0.008, depth=0.38, vertices=16); F.set_mat(ant, M_GREY); body(ant)
# hoses: backpack sides -> chest panel
for sx in (-1, 1):
    hose(f'hose{sx}', [(sx * 0.2, 0.36, 0.74), (sx * 0.31, 0.12, 0.70), (sx * 0.22, -0.16, 0.76), (sx * 0.07, -0.2, 0.99)], 0.016, M_HOSE, parent=root)

# legs (relaxed, bent, slightly apart)
def leg(sx, hip, knee, ankle, toe_dir):
    capsule('thigh', hip, knee, 0.105, 0.088, M_SUIT, parent=root)
    capsule('shin', knee, ankle, 0.085, 0.078, M_SUIT, parent=root)
    d1 = (Vector(knee) - Vector(hip)).normalized(); d2 = (Vector(ankle) - Vector(knee)).normalized()
    rings('hipr', Vector(hip) + d1 * 0.07, d1, 0.105, n=2, spacing=0.035, parent=root)
    rings('kneer', knee, (d1 + d2), 0.09, n=3, spacing=0.032, parent=root)
    band('legstripe', Vector(hip) + d1 * 0.2, d1, 0.107, M_BLUE, width=0.018, parent=root)
    # boot: oriented with the shin, toe toward toe_dir
    up = -d2; fwd = Vector(toe_dir); fwd = (fwd - up * fwd.dot(up)).normalized()
    M = frame(ankle, up, fwd)
    rings('cuffb', Vector(ankle) + up * 0.09, up, 0.082, m=M_NAVY, n=1, minor=0.02, parent=root)
    bm_ = rounded_box('boot', (0, 0.04, -0.04), (0.085, 0.14, 0.055), 0.04, M_SUIT, parent=root, segs=6, matrix=M)
    rounded_box('sole', (0, 0.045, -0.095), (0.082, 0.14, 0.014), 0.012, M_NAVY, parent=root, segs=3, matrix=M)
    rounded_box('bootcap', (0, 0.0, 0.03), (0.09, 0.1, 0.03), 0.028, M_NAVY, parent=root, segs=4, matrix=M)

leg(-1, (-0.14, 0.0, 0.66), (-0.22, -0.16, 0.26), (-0.24, 0.10, -0.03), (0, -1, 0))
leg(+1, (0.14, 0.0, 0.66), (0.27, -0.10, 0.27), (0.38, 0.24, 0.14), (0.2, -1, 0))

# left arm (relaxed, slightly out, bent)
def arm_segments(sh, el, wr, parent=None):
    capsule('uarm', sh, el, 0.08, 0.07, M_SUIT, parent=parent)
    capsule('farm', el, wr, 0.07, 0.062, M_SUIT, parent=parent)
    d1 = (Vector(el) - Vector(sh)).normalized(); d2 = (Vector(wr) - Vector(el)).normalized()
    rings('elbr', el, d1 + d2, 0.072, n=3, spacing=0.03, parent=parent)
    band('armstripe', Vector(sh) + d1 * 0.17, d1, 0.082, M_BLUE, width=0.016, parent=parent)
    rings('wristr', Vector(wr) - d2 * 0.015, d2, 0.064, m=M_NAVY, n=1, minor=0.02, parent=parent)
    return d2

def glove(M, parent=None, curl=0.5, thumb_side=1, grip=None):
    """glove in a local frame: +Z along forearm (toward fingers), palm normal -Y.
    grip=(proximal_len, distal_curl_y, distal_z): two-segment fingers for holding something."""
    palm = F.prim('sphere', 'palm', loc=(0, 0, 0.055), radius=1, segments=40, ring_count=24)
    palm.scale = (0.07, 0.038, 0.08); F.set_mat(palm, M_SUIT)
    objs = [palm]
    for i, x in enumerate((-0.042, -0.014, 0.014, 0.042)):
        ln = (0.075, 0.085, 0.08, 0.065)[i]
        a = Vector((x, 0, 0.105))
        if grip:
            pl, cy, cz = grip
            k = a + Vector((0, 0, pl * ln / 0.08))
            objs += capsule('finger', a, k, 0.016, 0.0155, M_SUIT)
            b = k + Vector((0, -cy, cz)) * (ln * 0.8)
            objs += capsule('finger', k, b, 0.0155, 0.014, M_SUIT)
        else:
            b = a + Vector((0, -curl * ln * 0.9, ln * (1 - curl * 0.5)))
            objs += capsule('finger', a, b, 0.016, 0.014, M_SUIT)
    a = Vector((thumb_side * 0.06, -0.01, 0.045)); b = a + Vector((thumb_side * 0.025, -0.04, 0.05))
    objs += capsule('thumb', a, b, 0.017, 0.015, M_SUIT)
    bpy.context.view_layer.update()
    for o in objs:
        o.matrix_world = M @ o.matrix_world
        if parent: o.parent = parent
    return objs

L_SH, L_EL, L_WR = (0.31, 0.0, 1.27), (0.57, 0.06, 1.08), (0.66, -0.24, 1.32)
d2 = arm_segments(L_SH, L_EL, L_WR, parent=root)
glove(frame(L_WR, d2, (0, -1, -0.3)), parent=root, curl=0.4, thumb_side=-1)

# ------------------------------------------------------------------ camera (defined first: the phone is placed in screen space)
CAM_POS = Vector((0.0, -3.65, 0.9)); CAM_TGT = (0.0, 0.0, 0.70); LENS = 42
PHONE_SX, PHONE_SY = 0.70, 0.63
cam = bpy.data.cameras.new('cam'); cam.lens = LENS; cam.sensor_width = 36
co = bpy.data.objects.new('cam', cam); F.link(co); co.location = CAM_POS
F.look_at(co, CAM_TGT); sc.camera = co
bpy.context.view_layer.update()

def screen_to_world(sx, sy, depth):
    """normalized screen coords (x right, y down) + distance along the view axis -> world point"""
    hw = 18.0 / LENS; hh = hw * 9 / 16
    d = Vector(((sx - 0.5) * 2 * hw, (0.5 - sy) * 2 * hh, -1.0)) * depth
    return co.matrix_world @ d

# ------------------------------------------------------------------ right arm + phone (world space, reaching to camera)
UA, FA = 0.72, 0.78                                   # upper arm / forearm lengths
R_SH_W = ROOT_M @ Vector((-0.31, -0.02, 1.27))
sh_depth = (co.matrix_world.inverted() @ R_SH_W).z * -1
PH_DEPTH = 1.2                                       # how far the phone is in front of the shoulder (along the view axis)
PHONE_C = screen_to_world(PHONE_SX, PHONE_SY, sh_depth - PH_DEPTH)
# clamp the lateral offset so the arm can reach (reach budget = UA+FA-0.03 incl. wrist->phone offset)
reach = UA + FA - 0.03 - 0.17
lat_max = math.sqrt(max(0.0, reach ** 2 - PH_DEPTH ** 2))
sh_at_depth = screen_to_world(*F.proj(R_SH_W), sh_depth - PH_DEPTH)
lat = PHONE_C - sh_at_depth
if lat.length > lat_max:
    print('clamping phone lateral offset', round(lat.length, 3), '->', round(lat_max, 3))
    PHONE_C = sh_at_depth + lat.normalized() * lat_max
print('phone screen', F.proj(PHONE_C), 'shoulder screen', F.proj(R_SH_W))
# phone frame: local -Y toward camera, local Z = screen up (right-handed: X = Y x Z)
f = (CAM_POS - PHONE_C).normalized()
up = Vector((0.18, 0, 1)); up = (up - f * up.dot(f)).normalized()
x = (-f).cross(up).normalized()
PH_M = Matrix((x, -f, up)).transposed().to_4x4(); PH_M.translation = PHONE_C
PH_M = PH_M @ Matrix.Rotation(math.radians(-12), 4, 'Y')   # slight tilt about the screen normal
build_phone(PH_M)
# glove gripping the phone, built in phone-local coords (X right, Y back, Z up). Palm behind the glass,
# four fingers wrap the left edge and show their tips over the glass, thumb runs up the right edge.
def grip_glove(M):
    yb = PT / 2
    objs = []
    palm = F.prim('sphere', 'rpalm', loc=(0.0, yb + 0.046, -0.075), radius=1, segments=48, ring_count=24)
    palm.scale = (0.078, 0.042, 0.088); palm.rotation_euler = (0, math.radians(-20), 0); F.set_mat(palm, M_SUIT); objs.append(palm)
    heel = F.prim('sphere', 'rheel', loc=(0.04, yb + 0.05, -0.135), radius=0.05, segments=40, ring_count=20); F.set_mat(heel, M_SUIT); objs.append(heel)
    xe = -PW / 2
    for i, z in enumerate((-0.105, -0.062, -0.019, 0.024)):
        r = (0.0165, 0.017, 0.0165, 0.015)[i]
        pts = [(-0.02, yb + 0.044, z), (xe - 0.012, yb + 0.03, z + 0.012), (xe - 0.016, -yb - 0.004, z + 0.02), (xe + 0.006, -yb - 0.02, z + 0.022)]
        for a, b in zip(pts[:-1], pts[1:]):
            objs += capsule('rfinger', a, b, r, r * 0.95, M_SUIT)
    tp = [(0.035, yb + 0.04, -0.12), (PW / 2 + 0.012, yb + 0.012, -0.075), (PW / 2 + 0.014, -yb - 0.004, -0.03), (PW / 2 - 0.004, -yb - 0.018, -0.01)]
    for a, b in zip(tp[:-1], tp[1:]):
        objs += capsule('rthumb', a, b, 0.018, 0.016, M_SUIT)
    bpy.context.view_layer.update()
    for o in objs:
        o.matrix_world = M @ o.matrix_world
    return M @ Vector((0.05, yb + 0.062, -0.17))     # wrist point (world)

R_WR_W = grip_glove(PH_M)
d = R_WR_W - R_SH_W; dist = d.length
print('arm reach needed', round(dist, 3), 'available', UA + FA)
if dist > UA + FA - 0.01:
    print('WARNING: arm over-reach', dist)
along = d / dist
hint = Vector((0.8, -0.2, -0.5)); perp = (hint - along * hint.dot(along)).normalized()
cosA = max(-1, min(1, (UA ** 2 + dist ** 2 - FA ** 2) / (2 * UA * dist)))
R_EL_W = R_SH_W + along * (UA * cosA) + perp * (UA * math.sqrt(max(0, 1 - cosA ** 2)))
d2w = arm_segments(R_SH_W, R_EL_W, R_WR_W)

# ------------------------------------------------------------------ lights
def area(name, loc, target, energy, size, color):
    d = bpy.data.lights.new(name, 'AREA'); d.energy = energy; d.size = size; d.color = color; d.shape = 'SQUARE'
    o = bpy.data.objects.new(name, d); F.link(o); o.location = loc; F.look_at(o, target); return o

sun = bpy.data.lights.new('sun', 'SUN'); sun.energy = 6.5; sun.angle = math.radians(3); sun.color = (1.0, 0.95, 0.86)
so = bpy.data.objects.new('sun', sun); F.link(so); so.location = (-4, -3.5, 6); F.look_at(so, (0, 0, 0.8))
area('fill_earth', (1.0, -2.5, -4.0), (0.2, 0, 0.6), 420, 6.0, F.lin('#6f85ff')[:3])
area('rim', (3.2, 4.5, 2.6), (0, 0, 0.9), 2200, 3.0, (0.85, 0.9, 1.0))
area('rim2', (-3.5, 3.5, 3.5), (0, 0, 1.2), 500, 3.0, (1.0, 0.95, 0.9))
area('front_soft', (3.5, -5.5, 1.5), (0, 0, 0.8), 70, 7.0, (0.8, 0.86, 1.0))

smooth_all()

print('proj head', F.proj(ROOT_M @ (HEAD + Vector((0, 0, HR)))), 'phone', F.proj(PHONE_C),
      'boots', F.proj(ROOT_M @ Vector((-0.24, 0.1, -0.1))), F.proj(ROOT_M @ Vector((0.36, 0.17, -0.1))),
      'lhand', F.proj(ROOT_M @ Vector(L_WR)))

if MODE == 'test':
    F.render(OUT, 1280, 720, 24)
elif MODE == 'hd':
    F.render(OUT, 1920, 1080, 96)
elif MODE == '4k':
    F.render(OUT, 3840, 2160, 160)
elif MODE == 'check':
    F.render(OUT, 1920, 1080, 32)
elif MODE == 'none':
    pass
