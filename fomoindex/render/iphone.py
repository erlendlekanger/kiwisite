"""A 4K render of an iPhone (Pro proportions, black titanium) showing the FOMOINDEX logo, on a transparent background,
lit with the same studio as the PACKHUNT pack (packhunt/brand/3d/common.py, the Axo recipe) so it can float at the
astronaut's glove in place of the pack.

    C:/Users/erlen/blender-5.2.2-windows-x64/blender.exe -b --factory-startup -P fomoindex/render/iphone.py -- \
        --screen <abs png> --out <abs png> [--res 2600x3600] [--samples 256] [--yaw 22] [--pitch -12] [--roll 14]
"""
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
HDRI = os.path.join(HERE, "..", "..", "axo", "brand", "3d", "hdri", "studio_small_09_2k.hdr")
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default):
    return argv[argv.index(name) + 1] if name in argv else default


def lin(hexcol):
    c = [int(hexcol.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in c) + (1.0,)


SCREEN = arg("--screen", os.path.join(HERE, "screen_center.png"))
OUT = arg("--out", os.path.join(HERE, "renders", "iphone.png"))
RX, RY = [int(v) for v in arg("--res", "2600x3600").split("x")]
SAMPLES = int(arg("--samples", 256))
YAW, PITCH, ROLL = float(arg("--yaw", 22)), float(arg("--pitch", -12)), float(arg("--roll", 14))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# iPhone Pro proportions in decimetres: 71.6 x 146.6 x 8.25 mm, corner radius about 12 mm
W, H, D, R = 0.716, 1.466, 0.0825, 0.118


def rrect(w, h, r, seg=24):
    pts = []
    for cx, cy, a0 in ((w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def slab(name, w, h, r, depth, z0, mat, bevel=0.0, bseg=6):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z0)) for x, y in rrect(w, h, r)]
    f = bm.faces.new(vs)
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in ext["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.z += depth
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    if bevel:
        m = ob.modifiers.new("bevel", "BEVEL")
        m.width, m.segments, m.limit_method = bevel, bseg, "ANGLE"
        m.angle_limit = math.radians(50)
        ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    return ob


def principled(name, color, rough=0.3, metallic=0.0, coat=0.0, coat_rough=0.03, aniso=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = lin(color)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metallic
    for n, v in (("Coat Weight", coat), ("Coat Roughness", coat_rough), ("Anisotropic", aniso)):
        if n in b.inputs:
            b.inputs[n].default_value = v
    return m


titanium = principled("titanium", "#5c5d62", rough=0.24, metallic=1.0, aniso=0.35)
glass = principled("glass", "#030304", rough=0.03, coat=1.0, coat_rough=0.01)
island = principled("island", "#000000", rough=0.45)
button = principled("button", "#45464b", rough=0.28, metallic=1.0)

# the display: the screen image as light under glossy glass
disp = bpy.data.materials.new("display")
disp.use_nodes = True
nt = disp.node_tree
bsdf = nt.nodes["Principled BSDF"]
bsdf.inputs["Base Color"].default_value = (0, 0, 0, 1)
bsdf.inputs["Roughness"].default_value = 0.04
bsdf.inputs["Coat Weight"].default_value = 1.0
bsdf.inputs["Coat Roughness"].default_value = 0.01
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load(SCREEN)
tex.interpolation = "Cubic"
nt.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
bsdf.inputs["Emission Strength"].default_value = 1.35

phone = []
phone.append(slab("frame", W, H, R, D, -D / 2, titanium, bevel=0.016))
phone.append(slab("glass", W - 0.008, H - 0.008, R - 0.004, 0.004, D / 2 - 0.002, glass, bevel=0.002, bseg=3))

# display surface with UVs over its bounds, inset by the bezel
bez = 0.019
dw, dh, dr = W - 0.008 - 2 * bez, H - 0.008 - 2 * bez, R - 0.004 - bez
me = bpy.data.meshes.new("display")
bm = bmesh.new()
vs = [bm.verts.new((x, y, D / 2 + 0.0021)) for x, y in rrect(dw, dh, dr, 32)]
f = bm.faces.new(vs)
uv = bm.loops.layers.uv.new()
for loop in f.loops:
    loop[uv].uv = ((loop.vert.co.x + dw / 2) / dw, (loop.vert.co.y + dh / 2) / dh)
bm.to_mesh(me)
bm.free()
dob = bpy.data.objects.new("display", me)
scene.collection.objects.link(dob)
dob.data.materials.append(disp)
phone.append(dob)

# dynamic island
isl = slab("island", 0.178, 0.052, 0.026, 0.0006, D / 2 + 0.0023, island)
isl.location.y = dh / 2 - 0.05
phone.append(isl)

# side buttons: action and volume on the left, side button on the right
for name, x, y, h in (("action", -W / 2 - 0.004, 0.43, 0.06), ("vol_up", -W / 2 - 0.004, 0.28, 0.11),
                      ("vol_dn", -W / 2 - 0.004, 0.13, 0.11), ("side", W / 2 + 0.004, 0.25, 0.17)):
    b = slab(name, 0.012, h, 0.005, 0.03, -0.015, button, bevel=0.003, bseg=3)
    b.location = (x, y, 0)
    phone.append(b)

rig = bpy.data.objects.new("rig", None)
scene.collection.objects.link(rig)
for o in phone:
    o.parent = rig
rig.rotation_euler = (math.radians(PITCH), math.radians(YAW), math.radians(ROLL))
rig.location = (0, 0, 1.0)

# world and studio: the Axo recipe, as in packhunt/brand/3d/common.py
w = bpy.data.worlds.new("world")
scene.world = w
w.use_nodes = True
wn = w.node_tree
env = wn.nodes.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(HDRI)
mp = wn.nodes.new("ShaderNodeMapping")
co = wn.nodes.new("ShaderNodeTexCoord")
mp.inputs["Rotation"].default_value = (0, 0, math.radians(140))
wn.links.new(co.outputs["Generated"], mp.inputs["Vector"])
wn.links.new(mp.outputs["Vector"], env.inputs["Vector"])
wn.nodes["Background"].inputs["Strength"].default_value = 0.11
wn.links.new(env.outputs["Color"], wn.nodes["Background"].inputs["Color"])


def softbox(name, loc, power, sx, sy, target=(0, 0, 1.0)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = sx, sy
    ld.energy = power
    lo = bpy.data.objects.new(name, ld)
    scene.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()


p = 0.5
softbox("key", (-4.0, 6.0, 6.5), 1050 * p, 5.0, 4.0)
softbox("strip_r", (6.0, 2.2, 2.5), 420 * p, 0.8, 6.0)
softbox("strip_l", (-6.0, 1.8, 1.0), 200 * p, 0.8, 6.0)
softbox("rim_l", (-4.5, 1.8, -6.5), 420 * p, 3.0, 2.0)
softbox("rim_r", (4.5, 1.8, -6.5), 420 * p, 3.0, 2.0)

# camera looks down -Z at the phone's front (the phone lies in the XY plane facing +Z)
cd = bpy.data.cameras.new("cam")
cd.lens = 120
cam = bpy.data.objects.new("cam", cd)
scene.collection.objects.link(cam)
cam.location = (0, 0, 1.0 + 9.2)
scene.camera = cam
cd.sensor_fit = "VERTICAL"
cd.sensor_height = 24

r = scene.render
r.engine = "CYCLES"
r.resolution_x, r.resolution_y = RX, RY
r.film_transparent = True
r.image_settings.file_format = "PNG"
r.image_settings.color_mode = "RGBA"
r.image_settings.color_depth = "8"
scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev_type in ("OPTIX", "CUDA"):
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        if any(d.type == dev_type for d in prefs.devices):
            break
    except TypeError:
        continue
for d in prefs.devices:
    d.use = d.type in ("OPTIX", "CUDA")
scene.cycles.device = "GPU"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
r.filepath = OUT
bpy.ops.render.render(write_still=True)
print("wrote", OUT)
