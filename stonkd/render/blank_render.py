"""Konsept-render av STONKD-mynter i Blender (Cycles).

Kjør: python3 coin_render.py <out.png> <bredde> <hoyde> <samples>
"""
import json
import math
import sys
from pathlib import Path

import bpy
import bmesh

HERE = Path(__file__).resolve().parent
SITE = HERE / "assets"
OUT = str(Path(sys.argv[1]).resolve()) if len(sys.argv) > 1 else str(HERE / "render.png")
W = int(sys.argv[2]) if len(sys.argv) > 2 else 1920
H = int(sys.argv[3]) if len(sys.argv) > 3 else 1080
SAMPLES = int(sys.argv[4]) if len(sys.argv) > 4 else 128

SHAPES = json.loads((SITE / "shapes.json").read_text())

bpy.ops.wm.read_factory_settings(use_empty=True)

# STONKD-merket «Stack»: samme rader som brand/stonkd/build.py, skalert inn i formkoordinatene.
STACK_H, STACK_GAP, STACK_W = 78, 28, 400
STACK_ROWS = [(0.20, 1.00), (0.00, 0.45), (0.15, 0.85), (0.55, 1.00), (0.00, 0.80)]
STACK_COLS = ["#ccedf9", "#aee0f3", "#8fd3ee", "#70c6e8", "#52b9e2"]


def pill(x0, y0, w, h, seg=24):
    """Pilleform (stadion) som polygon, y opp."""
    r = h / 2
    pts = []
    for cx, a0 in ((x0 + w - r, -90), (x0 + r, 90)):
        for k in range(seg + 1):
            a = math.radians(a0 + 180 * k / seg)
            pts.append([cx + r * math.cos(a), y0 + r + r * math.sin(a)])
    return pts


STACK_TALL = 5 * STACK_H + 4 * STACK_GAP
_s = 1.08 / STACK_TALL
for i, (a, b) in enumerate(STACK_ROWS):
    x = (a * STACK_W - STACK_W / 2) * _s
    y = (STACK_TALL / 2 - i * (STACK_H + STACK_GAP) - STACK_H) * _s
    SHAPES[f"STONKD_{i}"] = {"shapes": [{"outer": pill(x, y, (b - a) * STACK_W * _s, STACK_H * _s), "holes": []}]}

scene = bpy.context.scene


def hexcol(h, a=1.0):
    h = h.lstrip("#")
    srgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
    return (*lin, a)


# ------------------------------------------------------------------ materialer
def principled(name, **kw):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    for k, v in kw.items():
        b.inputs[k].default_value = v
    return m, b


def spun_metal(name, color, rough=0.28, aniso=0.85):
    """Dreid finish: anisotropisk refleks rundt myntens akse."""
    m, b = principled(name, **{"Base Color": hexcol(color), "Metallic": 1.0, "Roughness": rough,
                               "Anisotropic": aniso})
    nt = m.node_tree
    tan = nt.nodes.new("ShaderNodeTangent")
    tan.direction_type = "RADIAL"
    tan.axis = "Z"
    nt.links.new(tan.outputs["Tangent"], b.inputs["Tangent"])
    return m


def reeded_metal(name, color, count=180):
    """Riflet sidekant: bump fra en sinus rundt omkretsen."""
    m, b = principled(name, **{"Base Color": hexcol(color), "Metallic": 1.0, "Roughness": 0.22})
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    at = nt.nodes.new("ShaderNodeMath"); at.operation = "ARCTAN2"
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = count
    sn = nt.nodes.new("ShaderNodeMath"); sn.operation = "SINE"
    bump = nt.nodes.new("ShaderNodeBump"); bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.004
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["Y"], at.inputs[0])
    nt.links.new(sep.outputs["X"], at.inputs[1])
    nt.links.new(at.outputs[0], mul.inputs[0])
    nt.links.new(mul.outputs[0], sn.inputs[0])
    nt.links.new(sn.outputs[0], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def frosted_glass(name, color, rough=0.12, absorb=6.0):
    m, b = principled(name, **{"Base Color": (1, 1, 1, 1), "Transmission Weight": 1.0,
                               "Roughness": rough, "IOR": 1.52})
    nt = m.node_tree
    vol = nt.nodes.new("ShaderNodeVolumeAbsorption")
    vol.inputs["Color"].default_value = hexcol(color)
    vol.inputs["Density"].default_value = absorb
    nt.links.new(vol.outputs[0], nt.nodes["Material Output"].inputs["Volume"])
    return m


def enamel(name, color, metallic=0.0, rough=0.18):
    m, _ = principled(name, **{"Base Color": hexcol(color), "Metallic": metallic, "Roughness": rough,
                               "Coat Weight": 1.0, "Coat Roughness": 0.04})
    return m


def ink(name, png):
    """Logo med fargene fra en tekstur, mappet fra formens -1..1-koordinater."""
    m, b = principled(name, **{"Roughness": 0.16, "Coat Weight": 1.0, "Coat Roughness": 0.03,
                               "Metallic": 0.15})
    nt = m.node_tree
    tc = nt.nodes.new("ShaderNodeTexCoord")
    vm = nt.nodes.new("ShaderNodeVectorMath"); vm.operation = "MULTIPLY_ADD"
    vm.inputs[1].default_value = (0.5, 0.5, 0)
    vm.inputs[2].default_value = (0.5, 0.5, 0)
    img = nt.nodes.new("ShaderNodeTexImage")
    img.image = bpy.data.images.load(str(png))
    img.interpolation = "Cubic"
    nt.links.new(tc.outputs["Object"], vm.inputs[0])
    nt.links.new(vm.outputs[0], img.inputs["Vector"])
    nt.links.new(img.outputs["Color"], b.inputs["Base Color"])
    return m


# ------------------------------------------------------------------ geometri
# Myntprofilen fra scene.js (radius 1.6 i originalen, skalert til 1).
PROFILE = [(1.18, .1), (1.195, .115), (1.22, .124), (1.245, .115), (1.26, .106), (1.29, .106),
           (1.32, .13), (1.36, .147), (1.5, .152), (1.565, .137), (1.595, .1), (1.6, .07),
           (1.6, -.07), (1.595, -.1), (1.565, -.137), (1.5, -.152), (1.36, -.147), (1.32, -.13),
           (1.29, -.106), (1.26, -.106), (1.245, -.115), (1.22, -.124), (1.195, -.115), (1.18, -.1)]
PROFILE = [(r / 1.6, y / 1.6) for r, y in PROFILE]
FIELD_R = 1.18 / 1.6
FACE_Z = 0.1 / 1.6


def coin_mesh(name, rim_mat, edge_mat, face_mat, steps=256):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    ring = []
    for i in range(steps):
        a = 2 * math.pi * i / steps
        ca, sa = math.cos(a), math.sin(a)
        ring.append([bm.verts.new((r * ca, r * sa, z)) for r, z in PROFILE])
    n = len(PROFILE)
    for i in range(steps):
        a, b2 = ring[i], ring[(i + 1) % steps]
        for j in range(n - 1):
            f = bm.faces.new((a[j], b2[j], b2[j + 1], a[j + 1]))
            r0 = PROFILE[j][0]; r1 = PROFILE[j + 1][0]
            f.material_index = 1 if (abs(r0 - 1) < 1e-3 and abs(r1 - 1) < 1e-3) else 0
            f.smooth = True
    # flatene, med et senterpunkt og konsentriske ringer for jevn skygge
    for side, j in ((1, 0), (-1, n - 1)):
        z = FACE_Z * side
        prev = [ring[i][j] for i in range(steps)]
        for k in range(1, 8):
            rr = FIELD_R * (1 - k / 8)
            cur = [bm.verts.new((rr * math.cos(2 * math.pi * i / steps), rr * math.sin(2 * math.pi * i / steps), z))
                   for i in range(steps)]
            for i in range(steps):
                q = (prev[i], prev[(i + 1) % steps], cur[(i + 1) % steps], cur[i])
                f = bm.faces.new(q if side > 0 else q[::-1])
                f.material_index = 2; f.smooth = True
            prev = cur
        c = bm.verts.new((0, 0, z))
        for i in range(steps):
            t = (prev[i], prev[(i + 1) % steps], c)
            f = bm.faces.new(t if side > 0 else t[::-1])
            f.material_index = 2; f.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    for m in (rim_mat, edge_mat, face_mat):
        me.materials.append(m)
    bpy.context.collection.objects.link(ob)
    ob.modifiers.new("smooth", "WEIGHTED_NORMAL")
    return ob


def logo(name, key, mat, side=1, depth=0.022):
    spec = SHAPES[key]
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "2D"
    cu.fill_mode = "BOTH"
    cu.extrude = depth / 2
    cu.bevel_depth = 0.006
    cu.bevel_resolution = 4
    for sh in spec["shapes"]:
        for loop in [sh["outer"], *sh["holes"]]:
            sp = cu.splines.new("POLY")
            sp.points.add(len(loop) - 1)
            for p, (x, y) in zip(sp.points, loop):
                p.co = (x, y, 0, 1)
            sp.use_cyclic_u = True
    ob = bpy.data.objects.new(name, cu)
    ob.data.materials.append(mat)
    bpy.context.collection.objects.link(ob)
    ob.location.z = side * (FACE_Z + depth / 2 + 0.004)
    if side < 0:
        ob.rotation_euler.y = math.pi
    return ob


def mark(name, key, mat, side=1):
    if key != "STONKD":
        return [logo(name, key, mat, side)]
    return [logo(f"{name}_{i}", f"STONKD_{i}", MAT[f"stack_{i}"], side) for i in range(5)]


def make_coin(name, front_key, front_mat, rim_mat, edge_mat, face_mat, back=True):
    body = coin_mesh(name + "_body", rim_mat, edge_mat, face_mat)
    parts = [body, *mark(name + "_logo", front_key, front_mat)]
    if back:                             # glassmynten viser baksiden gjennom flaten, saa den faar ingen
        parts += mark(name + "_back", "STONKD", None, side=-1)
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    for o in parts:
        o.parent = root
    return root


# ------------------------------------------------------------------ scene
MAT = {
    "steel_rim": spun_metal("steel_rim", "#c9cdd2", rough=0.18, aniso=0.3),
    "steel_face": spun_metal("steel_face", "#b8bcc2", rough=0.3, aniso=0.9),
    "steel_edge": reeded_metal("steel_edge", "#c2c6cb"),
    "glass": frosted_glass("glass", "#52b9e2", rough=0.08, absorb=3.5),
    "glass_face": frosted_glass("glass_face", "#52b9e2", rough=0.5, absorb=5.0),
    "ink_s": ink("ink_s", SITE / "STONKED_ink.png"),
    "ink_sol": ink("ink_sol", SITE / "SOL_ink.png"),
    "chrome": spun_metal("chrome", "#e6ecf0", rough=0.06, aniso=0.0),
    "apple": enamel("apple", "#16191d", metallic=1.0, rough=0.12),
}
for _i, _c in enumerate(STACK_COLS):
    MAT[f"stack_{_i}"] = enamel(f"stack_{_i}", _c, rough=0.14)



# Tom staalmynt rett forfra, gjennomsiktig bakgrunn. Logoen legges paa i CSS.
coin = coin_mesh("blank", MAT["steel_rim"], MAT["steel_edge"], MAT["steel_face"])
cam = bpy.data.cameras.new("cam")
cam.type = "ORTHO"
cam.ortho_scale = 2.08
co = bpy.data.objects.new("cam", cam)
scene.collection.objects.link(co)
co.location = (0, 0, 6)
scene.camera = co

# ------------------------------------------------------------------ lys
def area(name, loc, rot, size, energy, color="#ffffff", shape="RECTANGLE", sy=None):
    li = bpy.data.lights.new(name, "AREA")
    li.shape = shape
    li.size = size
    if sy:
        li.size_y = sy
    li.energy = energy
    li.color = hexcol(color)[:3]
    ob = bpy.data.objects.new(name, li)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    bpy.context.collection.objects.link(ob)
    return ob


area("top", (0, -1, 6), (10, 0, 0), 6, 900, sy=2.5)
area("strip_l", (-4.5, -1.5, 2.2), (75, 0, -70), 0.6, 450, sy=5)
area("rim_r", (4.6, 3.0, 2.6), (65, 0, 120), 0.5, 520, color="#52b9e2", sy=5)
area("back", (0, 5, 2.5), (-90, 0, 0), 4, 260, color="#8fd4f1", sy=2)
area("fill", (0, -8, 1.5), (90, 0, 0), 10, 35, sy=4)

world = bpy.data.worlds.new("w")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = hexcol("#050c10")
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0
scene.world = world


# lysene staar rundt en staaende mynt; her ligger mynten, saa vi snur hele riggen
for o in bpy.data.objects:
    if o.type == "LIGHT":
        x, y, z = o.location
        o.location = (x, -z + 3.0, y + 3.5)
        o.rotation_euler.x -= math.radians(90)
area("dome", (2.2, 2.8, 9), (-16, 12, 0), 4, 520, sy=3)
area("rim_blue", (-3.5, -3.5, 2.5), (55, 0, -45), 1.2, 700, color="#52b9e2", sy=5)
scene.world.node_tree.nodes["Background"].inputs[0].default_value = hexcol("#1b2b33")
scene.render.film_transparent = True
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.render.resolution_x = W
scene.render.resolution_y = H
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print("wrote", OUT)
