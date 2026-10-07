"""FOMOCARD hero video: a black-rock vault lit by one ceiling light box, a brushed
aluminium plinth, a mirror-black metal card on an acrylic stand, slow dolly-in.

Run:  python scene.py --out DIR [--res 1280 800] [--frames 1 240]
      [--samples 24] [--still FRAME] [--card blue|black]
Needs `pip install bpy` (Blender as a Python module). Textures (Poly Haven, CC0)
live in ./tex.
"""
import argparse
import math
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "tex")

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--res", nargs=2, type=int, default=[1280, 800])
ap.add_argument("--frames", nargs=2, type=int, default=[1, 240])
ap.add_argument("--samples", type=int, default=24)
ap.add_argument("--still", type=int, default=None)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--card", default="black")
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])
CARD_PNG = os.path.join(HERE, "..", "fomocard_front_black.png" if args.card == "black"
                        else "fomocard_front.png")

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# ---------------------------------------------------------------- helpers
def node_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m, m.node_tree, m.node_tree.nodes["Principled BSDF"]


def img(nt, path, non_color=False):
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(path, check_existing=True)
    if non_color:
        t.image.colorspace_settings.name = "Non-Color"
    return t


def pbr(name, base, value=1.0, rough_mul=1.0):
    """Poly Haven PBR set: colour (darkened by `value`), roughness, normal."""
    m, nt, b = node_mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    d = img(nt, f"{TEX}/{base}_diff.jpg")
    r = img(nt, f"{TEX}/{base}_rough.jpg", True)
    n = img(nt, f"{TEX}/{base}_nor.jpg", True)
    for t in (d, r, n):
        nt.links.new(tc.outputs["UV"], t.inputs["Vector"])
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = 0.25
    hsv.inputs["Value"].default_value = value
    nt.links.new(d.outputs["Color"], hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], b.inputs["Base Color"])
    rm = nt.nodes.new("ShaderNodeMath")
    rm.operation = "MULTIPLY"
    rm.inputs[1].default_value = rough_mul
    nt.links.new(r.outputs["Color"], rm.inputs[0])
    nt.links.new(rm.outputs[0], b.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def displaced_plane(name, size, loc, rot, mat, tex_base, uv_scale, strength, cuts):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=cuts[0], y_subdivisions=cuts[1],
                                    size=1, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    # UVs in metres so the texture keeps its real size
    uv = ob.data.uv_layers.active
    for poly in ob.data.polygons:
        for li in poly.loop_indices:
            co = ob.data.vertices[ob.data.loops[li].vertex_index].co
            uv.data[li].uv = (co.x / uv_scale, co.y / uv_scale)
    t = bpy.data.textures.new(name + "_disp", "IMAGE")
    t.image = bpy.data.images.load(f"{TEX}/{tex_base}_disp.jpg", check_existing=True)
    t.image.colorspace_settings.name = "Non-Color"
    mod = ob.modifiers.new("disp", "DISPLACE")
    mod.texture = t
    mod.texture_coords = "UV"
    mod.strength = strength
    mod.mid_level = 0.5
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def box(name, size, loc, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = ob.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 4
    ob.data.materials.append(mat)
    return ob


def rounded_rect(w, h, r, seg=12):
    pts = []
    for cx, cy, a0 in [(w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90),
                       (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)]:
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def mesh_obj(name, verts, faces, uvs=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    if uvs:
        uv = me.uv_layers.new()
        for poly in me.polygons:
            for li in poly.loop_indices:
                uv.data[li].uv = uvs[me.loops[li].vertex_index]
    me.update()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    return ob


# ---------------------------------------------------------------- materials
rock = pbr("rock", "dark_rock", value=0.55)
ground = pbr("ground", "rocks_ground_02", value=0.07, rough_mul=1.0)

alu, nt, b = node_mat("alu")
b.inputs["Base Color"].default_value = (0.32, 0.33, 0.35, 1)
b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.26
b.inputs["Anisotropic"].default_value = 0.7

base_m, nt, b = node_mat("plinth_base")
b.inputs["Base Color"].default_value = (0.02, 0.02, 0.022, 1)
b.inputs["Roughness"].default_value = 0.5

acr, nt, b = node_mat("acrylic")
b.inputs["Base Color"].default_value = (0.95, 0.97, 1.0, 1)
b.inputs["Roughness"].default_value = 0.02
b.inputs["Transmission Weight"].default_value = 1.0
b.inputs["IOR"].default_value = 1.49

body, nt, b = node_mat("card_body")
b.inputs["Base Color"].default_value = (0.02, 0.02, 0.022, 1)
b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.18

# card face: dark areas are mirror-black metal, silver artwork is satin metal
front, nt, b = node_mat("card_front")
tex = img(nt, CARD_PNG)
tex.interpolation = "Cubic"
nt.links.new(tex.outputs["Color"], b.inputs["Base Color"])
bw = nt.nodes.new("ShaderNodeRGBToBW")
nt.links.new(tex.outputs["Color"], bw.inputs["Color"])
for socket, lo, hi in [("Metallic", 1.0, 0.55), ("Roughness", 0.07, 0.28)]:
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = 0.10
    mr.inputs["From Max"].default_value = 0.45
    mr.inputs["To Min"].default_value = lo
    mr.inputs["To Max"].default_value = hi
    nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
    nt.links.new(mr.outputs["Result"], b.inputs[socket])
b.inputs["Coat Weight"].default_value = 0.6
b.inputs["Coat Roughness"].default_value = 0.02
nt.links.new(tex.outputs["Alpha"], b.inputs["Alpha"])

panel_m, nt, b = node_mat("panel")
nt.nodes.remove(b)
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Strength"].default_value = 14.0
em.inputs["Color"].default_value = (1.0, 0.985, 0.96, 1)
nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])

# ---------------------------------------------------------------- vault
# a narrow rock chamber: back wall 2.6 m behind the plinth, side walls 2.6 m out
R90 = math.radians(90)
displaced_plane("floor", (7, 14), (0, 0, 0), (0, 0, 0), ground, "rocks_ground_02",
                2.0, 0.10, (280, 560))
displaced_plane("back", (7, 5.5), (0, 2.6, 2.6), (R90, 0, 0), rock, "dark_rock",
                2.2, 0.35, (350, 275))
displaced_plane("left", (14, 5.5), (-2.6, 0, 2.6), (R90, 0, -R90), rock, "dark_rock",
                2.2, 0.35, (700, 275))
displaced_plane("right", (14, 5.5), (2.6, 0, 2.6), (R90, 0, R90), rock, "dark_rock",
                2.2, 0.35, (700, 275))
displaced_plane("ceiling", (7, 14), (0, 0, 4.4), (math.pi, 0, 0), rock, "dark_rock",
                2.2, 0.25, (200, 400))
# recessed light box above the plinth
box("panel", (1.9, 1.2, 0.02), (0, 0.15, 4.25), panel_m)
for x, y, sx, sy in [(0, 0.78, 2.1, 0.06), (0, -0.48, 2.1, 0.06), (-1.03, 0.15, 0.06, 1.3),
                     (1.03, 0.15, 0.06, 1.3)]:
    box("panel_frame", (sx, sy, 0.3), (x, y, 4.3), base_m)
bpy.ops.object.light_add(type="AREA", location=(0, 0.15, 4.22))
L = bpy.context.active_object
L.data.shape = "RECTANGLE"
L.data.size, L.data.size_y = 1.9, 1.2
L.data.energy = 1100
L.data.spread = math.radians(70)

# plinth: dark base with a brushed aluminium slab on top
box("plinth_base", (1.5, 0.95, 0.30), (0, 0, 0.15), base_m, bevel=0.006)
box("plinth_top", (1.62, 1.05, 0.06), (0, 0, 0.33), alu, bevel=0.004)
box("stand", (0.40, 0.09, 0.045), (0, 0, 0.3825), acr, bevel=0.004)

# ---------------------------------------------------------------- card
W, H, Rr, T = 0.856, 0.540, 0.034, 0.010
pts = rounded_rect(W, H, Rr)
n = len(pts)
verts = [(x, y, 0) for x, y in pts] + [(x, y, -T) for x, y in pts]
faces = [list(range(n)), list(range(2 * n - 1, n - 1, -1))]
faces += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
card_body = mesh_obj("card_body", verts, faces)
card_body.data.materials.append(body)
card_front = mesh_obj("card_front", [(x, y, 0.0004) for x, y in pts], [list(range(n))],
                      [((x + W / 2) / W, (y + H / 2) / H) for x, y in pts])
card_front.data.materials.append(front)
pivot = bpy.data.objects.new("card", None)
scene.collection.objects.link(pivot)
pivot.location = (0, 0.005, 0.36 + H / 2 + 0.025)
for ob in (card_body, card_front):
    ob.parent = pivot
    ob.rotation_euler = (R90, 0, 0)
pivot.rotation_euler[2] = math.radians(-16)
pivot.keyframe_insert("rotation_euler", frame=1)
pivot.rotation_euler[2] = 0
pivot.keyframe_insert("rotation_euler", frame=160)

# light strip that slides a highlight across the mirror-black face
bpy.ops.object.light_add(type="AREA", location=(-2.0, -1.9, 1.5))
S = bpy.context.active_object
S.data.shape = "RECTANGLE"
S.data.size, S.data.size_y = 0.12, 2.4
S.data.energy = 160
S.visible_camera = False
S.rotation_euler = (R90, 0, math.radians(-35))
S.keyframe_insert("location", frame=1)
S.location = (2.2, -1.9, 1.5)
S.keyframe_insert("location", frame=240)
# big soft reflector behind the camera: only seen as a sheen in the black face
bpy.ops.object.light_add(type="AREA", location=(0.0, -4.6, 1.15))
F = bpy.context.active_object
F.data.shape = "RECTANGLE"
F.data.size, F.data.size_y = 3.2, 0.5
F.data.energy = 45
F.rotation_euler = (math.radians(90), 0, 0)
F.visible_diffuse = False
F.visible_camera = False
# faint front fill, invisible in reflections, so the silver artwork reads
bpy.ops.object.light_add(type="AREA", location=(0.3, -3.0, 1.3))
K = bpy.context.active_object
K.data.size = 2.0
K.data.energy = 25
K.rotation_euler = (math.radians(80), 0, 0)
K.visible_glossy = False

# ---------------------------------------------------------------- camera
bpy.ops.object.camera_add()
cam = bpy.context.active_object
scene.camera = cam
target = bpy.data.objects.new("target", None)
scene.collection.objects.link(target)
con = cam.constraints.new("TRACK_TO")
con.target = target
con.track_axis = "TRACK_NEGATIVE_Z"
con.up_axis = "UP_Y"
cam.data.sensor_width = 36
cam.data.dof.use_dof = True
cam.data.dof.focus_object = card_front
cam.data.dof.aperture_fstop = 2.8
# start looking up at the light box, tilt down onto the plinth, push in
keys = [(1, (0.0, -6.4, 1.5), 3.0, 20), (100, (0.0, -4.6, 1.25), 0.85, 30),
        (240, (0.10, -2.35, 0.86), 0.66, 50)]
for f, loc, tz, lens in keys:
    cam.location = loc
    cam.data.lens = lens
    target.location = (0, 0, tz)
    cam.keyframe_insert("location", frame=f)
    cam.data.keyframe_insert("lens", frame=f)
    target.keyframe_insert("location", frame=f)

# ---------------------------------------------------------------- render
world = bpy.data.worlds.new("w")
world.color = (0, 0, 0)
scene.world = world
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = args.samples
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 6
scene.cycles.transmission_bounces = 6
scene.render.use_persistent_data = True
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Punchy"
scene.render.resolution_x, scene.render.resolution_y = args.res
scene.render.fps = args.fps
scene.render.image_settings.file_format = "PNG"
scene.frame_start, scene.frame_end = args.frames
os.makedirs(args.out, exist_ok=True)

if args.still is not None:
    scene.frame_set(args.still)
    scene.render.filepath = os.path.join(args.out, f"still_{args.still:04d}.png")
    bpy.ops.render.render(write_still=True)
else:
    scene.render.filepath = os.path.join(args.out, "f_")
    bpy.ops.render.render(animation=True)
