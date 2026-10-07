"""FOMOCARD hero film, rebuilt after the composition of moto-card.com's hero:
a dark room, a recessed ceiling light box that fades on, a rock wall standing on a
raised stage with rubble along its lit edge, a black column plinth with a brushed
metal top, and the card upright in a clear acrylic block. The camera travels straight
in and settles; then a light glint sweeps across the plinth.

  python moto_scene.py --mode intro --out DIR [--frames 1 240]   # plays once
  python moto_scene.py --mode loop  --out DIR [--frames 1 96]    # seamless glint loop
  add --still N to render one frame; --res W H; --samples N
"""
import argparse
import math
import os
import random
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
TEX = os.path.join(HERE, "tex")
FRONT = os.path.join(HERE, "..", "fomocard_front_black.png")
BACK = os.path.join(HERE, "..", "fomocard_back_black.png")

ap = argparse.ArgumentParser()
ap.add_argument("--out", required=True)
ap.add_argument("--mode", default="intro", choices=["intro", "loop"])
ap.add_argument("--res", nargs=2, type=int, default=[1280, 800])
ap.add_argument("--frames", nargs=2, type=int, default=None)
ap.add_argument("--samples", type=int, default=16)
ap.add_argument("--still", type=int, default=None)
args = ap.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:])

INTRO_LEN, LOOP_LEN = 240, 96
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
R90 = math.radians(90)


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


def rock_mat(name, value, base="rock_face_03"):
    m, nt, b = node_mat(name)
    tc = nt.nodes.new("ShaderNodeTexCoord")
    d, r, n = img(nt, f"{TEX}/{base}_diff.jpg"), img(nt, f"{TEX}/{base}_rough.jpg", True), img(nt, f"{TEX}/{base}_nor.jpg", True)
    for t in (d, r, n):
        nt.links.new(tc.outputs["UV"], t.inputs["Vector"])
    hsv = nt.nodes.new("ShaderNodeHueSaturation")
    hsv.inputs["Saturation"].default_value = 0.0
    hsv.inputs["Value"].default_value = value
    nt.links.new(d.outputs["Color"], hsv.inputs["Color"])
    nt.links.new(hsv.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(r.outputs["Color"], b.inputs["Roughness"])
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    return m


def box(name, size, loc, mat, bevel=0.0, segs=3):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = ob.modifiers.new("bevel", "BEVEL")
        mod.width = bevel
        mod.segments = segs
        ob.modifiers.new("wn", "WEIGHTED_NORMAL")
    if isinstance(mat, list):
        for m in mat:
            ob.data.materials.append(m)
    else:
        ob.data.materials.append(mat)
    return ob


def displaced_plane(name, size, loc, rot, mat, uv_scale, strength, cuts, tex="dark_rock"):
    bpy.ops.mesh.primitive_grid_add(x_subdivisions=cuts[0], y_subdivisions=cuts[1], size=1, location=loc, rotation=rot)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    uv = ob.data.uv_layers.active
    for poly in ob.data.polygons:
        for li in poly.loop_indices:
            co = ob.data.vertices[ob.data.loops[li].vertex_index].co
            uv.data[li].uv = (co.x / uv_scale, co.y / uv_scale)
    t = bpy.data.textures.new(name + "_d", "IMAGE")
    t.image = bpy.data.images.load(f"{TEX}/{tex}_disp.jpg", check_existing=True)
    t.image.colorspace_settings.name = "Non-Color"
    mod = ob.modifiers.new("disp", "DISPLACE")
    mod.texture, mod.texture_coords, mod.strength, mod.mid_level = t, "UV", strength, 0.5
    ob.data.materials.append(mat)
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


def rounded_rect(w, h, r, seg=10):
    pts = []
    for cx, cy, a0 in [(w / 2 - r, h / 2 - r, 0), (-w / 2 + r, h / 2 - r, 90), (-w / 2 + r, -h / 2 + r, 180), (w / 2 - r, -h / 2 + r, 270)]:
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


def card_face_mat(name, path):
    """Mirror-black metal with the print laser-engraved: the print also drives a bump."""
    m, nt, b = node_mat(name)
    t = img(nt, path)
    t.interpolation = "Cubic"
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    bw = nt.nodes.new("ShaderNodeRGBToBW")
    nt.links.new(t.outputs["Color"], bw.inputs["Color"])
    for sock, lo, hi in [("Metallic", 1.0, 0.6), ("Roughness", 0.08, 0.32)]:
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.10, 0.45
        mr.inputs["To Min"].default_value, mr.inputs["To Max"].default_value = lo, hi
        nt.links.new(bw.outputs["Val"], mr.inputs["Value"])
        nt.links.new(mr.outputs["Result"], b.inputs[sock])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.invert = True
    bump.inputs["Strength"].default_value = 0.6
    bump.inputs["Distance"].default_value = 0.0006
    nt.links.new(bw.outputs["Val"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Coat Weight"].default_value = 0.5
    b.inputs["Coat Roughness"].default_value = 0.03
    nt.links.new(t.outputs["Alpha"], b.inputs["Alpha"])
    return m


# ---------------------------------------------------------------- materials
rock = rock_mat("rock", 0.04)
rubble_m = rock_mat("rubble", 0.22)

black_satin, nt, b = node_mat("black_satin")
b.inputs["Base Color"].default_value = (0.006, 0.006, 0.007, 1)
b.inputs["Roughness"].default_value = 0.45
b.inputs["Specular IOR Level"].default_value = 0.6

floor_m, nt, b = node_mat("floor")
b.inputs["Base Color"].default_value = (0.0012, 0.0012, 0.0014, 1)
b.inputs["Roughness"].default_value = 0.85
b.inputs["Specular IOR Level"].default_value = 0.15

slab_top, nt, b = node_mat("slab_top")             # brushed aluminium
b.inputs["Base Color"].default_value = (0.36, 0.37, 0.39, 1)
b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.34
b.inputs["Anisotropic"].default_value = 0.8
slab_side, nt, b = node_mat("slab_side")
b.inputs["Base Color"].default_value = (0.04, 0.04, 0.045, 1)
b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.18

acrylic, nt, b = node_mat("acrylic")
b.inputs["Base Color"].default_value = (0.95, 0.97, 1.0, 1)
b.inputs["Roughness"].default_value = 0.03
b.inputs["Transmission Weight"].default_value = 1.0
b.inputs["IOR"].default_value = 1.49

card_edge, nt, b = node_mat("card_edge")
b.inputs["Base Color"].default_value = (0.5, 0.52, 0.55, 1)
b.inputs["Metallic"].default_value = 1.0
b.inputs["Roughness"].default_value = 0.22

box_inner, nt, b = node_mat("box_inner")           # inside walls of the ceiling light box
b.inputs["Base Color"].default_value = (0.8, 0.8, 0.82, 1)
b.inputs["Roughness"].default_value = 0.6
b.inputs["Emission Color"].default_value = (0.9, 0.9, 0.92, 1)
inner_glow = b.inputs["Emission Strength"]          # the walls glow with the panel
panel_m, nt, b = node_mat("panel")
nt.nodes.remove(b)
em = nt.nodes.new("ShaderNodeEmission")
em.inputs["Color"].default_value = (1.0, 0.99, 0.97, 1)
nt.links.new(em.outputs[0], nt.nodes["Material Output"].inputs["Surface"])
panel_strength = em.inputs["Strength"]

# ---------------------------------------------------------------- room
box("floor", (24, 24, 0.1), (0, 0, -0.05), floor_m)
# raised stage the rock wall stands on; its lit front edge reads as a bright line
STAGE_Y, STAGE_H = 1.3, 0.9
box("stage", (16, 6, STAGE_H), (0, STAGE_Y + 3, STAGE_H / 2), black_satin, bevel=0.01)
WALL_H = 4.6 - STAGE_H
displaced_plane("wall", (16, WALL_H), (0, STAGE_Y + 0.9, STAGE_H + WALL_H / 2), (R90, 0, 0), rock, 3.2, 0.3, (480, 120), tex="rock_face_03")
# rubble along the stage edge, in front of the wall
random.seed(3)
for i in range(520):
    x = random.uniform(-6, 6)
    s = random.uniform(0.015, 0.06)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=s, location=(x, STAGE_Y + random.uniform(0.05, 0.9), STAGE_H + s * 0.15))
    ob = bpy.context.active_object
    ob.scale = (random.uniform(1.0, 2.2), random.uniform(0.8, 1.6), random.uniform(0.25, 0.55))
    ob.rotation_euler = (random.random() * 3, random.random() * 3, random.random() * 3)
    t = bpy.data.textures.new(f"rub{i}", "VORONOI")
    t.noise_scale = 0.25
    mod = ob.modifiers.new("d", "DISPLACE")
    mod.texture, mod.strength = t, s * 0.5
    ob.data.materials.append(rubble_m)
box("ceiling", (24, 24, 0.1), (0, 0, 4.65), black_satin)

# recessed light box in the ceiling
BOX_C, BOX_W, BOX_D, BOX_Z, BOX_H = (0, 0.6), 4.6, 3.0, 4.6, 1.1
box("box_top", (BOX_W, BOX_D, 0.02), (BOX_C[0], BOX_C[1], BOX_Z + BOX_H), panel_m)
for x, y, sx, sy in [(0, BOX_D / 2, BOX_W, 0.02), (0, -BOX_D / 2, BOX_W, 0.02), (BOX_W / 2, 0, 0.02, BOX_D), (-BOX_W / 2, 0, 0.02, BOX_D)]:
    box("box_wall", (sx, sy, BOX_H), (BOX_C[0] + x, BOX_C[1] + y, BOX_Z + BOX_H / 2), box_inner)
bpy.ops.object.light_add(type="AREA", location=(BOX_C[0], BOX_C[1], BOX_Z + BOX_H - 0.05))
key = bpy.context.active_object
key.data.shape, key.data.size, key.data.size_y = "RECTANGLE", 1.1, 1.0
key.data.spread = math.radians(22)
key.location = (0, 0, BOX_Z + BOX_H - 0.05)          # aimed at the plinth, not the wall
# a hole in the ceiling for the box
cut = bpy.data.objects["ceiling"].modifiers.new("hole", "BOOLEAN")
hole = box("hole", (BOX_W, BOX_D, 1), (BOX_C[0], BOX_C[1], 4.65), black_satin)
cut.object, cut.operation = hole, "DIFFERENCE"
hole.hide_render = hole.hide_viewport = True

# faint grazing light on the wall so the rock reads
bpy.ops.object.light_add(type="AREA", location=(0, STAGE_Y + 0.2, 4.4))
graze = bpy.context.active_object
graze.data.shape, graze.data.size, graze.data.size_y = "RECTANGLE", 12, 0.3
graze.rotation_euler = (math.radians(-28), 0, 0)
graze.visible_glossy = False
# a wide strip over the stage edge: the bright, sparkling line of rubble along the wall
bpy.ops.object.light_add(type="AREA", location=(0, STAGE_Y + 0.45, 3.2))
rimL = bpy.context.active_object
rimL.data.shape, rimL.data.size, rimL.data.size_y = "RECTANGLE", 14, 0.5
rimL.data.spread = math.radians(25)
rimL.visible_glossy = False

# ---------------------------------------------------------------- plinth + card
COL_W, COL_H = 0.95, 1.05
box("column", (COL_W, COL_W, COL_H), (0, 0, COL_H / 2), black_satin, bevel=0.006)
SLAB = (1.2, 1.12, 0.085)
slab = box("slab", SLAB, (0, 0, COL_H + SLAB[2] / 2), [slab_side, slab_top], bevel=0.004)
for p in slab.data.polygons:                         # top face gets the brushed metal
    p.material_index = 1 if p.normal.z > 0.9 else 0
TOP = COL_H + SLAB[2]
box("acrylic", (0.3, 0.085, 0.045), (0, 0, TOP + 0.0225), acrylic, bevel=0.004)

CW = 0.56
CH, CR, CT = CW * 54 / 85.6, CW * 0.04, 0.009
pts = rounded_rect(CW, CH, CR)
n = len(pts)
body = mesh_obj("card_body", [(x, y, 0) for x, y in pts] + [(x, y, -CT) for x, y in pts],
                [list(range(n)), list(range(2 * n - 1, n - 1, -1))] + [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)])
body.data.materials.append(card_edge)
uvs = [((x + CW / 2) / CW, (y + CH / 2) / CH) for x, y in pts]
front = mesh_obj("card_front", [(x, y, 0.0003) for x, y in pts], [list(range(n))], uvs)
front.data.materials.append(card_face_mat("front", FRONT))
back = mesh_obj("card_back", [(-x, y, -CT - 0.0003) for x, y in pts], [list(range(n))[::-1]], uvs)
back.data.materials.append(card_face_mat("back", BACK))
for ob in (body, front, back):
    ob.rotation_euler = (R90, 0, 0)
    ob.location = (0, -0.004, TOP + CH / 2 + 0.02)

# ---------------------------------------------------------------- glint: a strip seen only in reflections
bpy.ops.object.light_add(type="AREA")
glint = bpy.context.active_object
glint.data.shape, glint.data.size, glint.data.size_y = "RECTANGLE", 0.35, 6.0
glint.data.energy = 0
glint.rotation_euler = (math.radians(70), 0, 0)
glint.visible_diffuse = False
glint.visible_camera = False


# the glint only touches the plinth and the card, never the room
recv = bpy.data.collections.new("glint_receivers")
scene.collection.children.link(recv)
for name in ("slab", "column", "acrylic", "card_body", "card_front", "card_back"):
    recv.objects.link(bpy.data.objects[name])
glint.light_linking.receiver_collection = recv


def glint_sweep(f0, f1, energy=75):
    """slide the strip from left to right, in front of and above the plinth"""
    for f, x, e in [(f0 - 1, -3.2, 0), (f0, -3.2, energy), (f1, 3.2, energy), (f1 + 1, 3.2, 0)]:
        glint.location = (x, -1.8, 2.6)
        glint.data.energy = e
        glint.keyframe_insert("location", frame=f)
        glint.data.keyframe_insert("energy", frame=f)


# ---------------------------------------------------------------- camera
bpy.ops.object.camera_add()
cam = bpy.context.active_object
scene.camera = cam
target = bpy.data.objects.new("target", None)
scene.collection.objects.link(target)
con = cam.constraints.new("TRACK_TO")
con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
cam.data.sensor_width = 36
cam.data.dof.use_dof = True
cam.data.dof.focus_object = front
cam.data.dof.aperture_fstop = 5.6
END = dict(loc=(0, -3.0, TOP + 0.36), tz=TOP + 0.25, lens=50)


def cam_key(f, loc, tz, lens):
    cam.location, target.location, cam.data.lens = loc, (0, 0, tz), lens
    cam.keyframe_insert("location", frame=f)
    target.keyframe_insert("location", frame=f)
    cam.data.keyframe_insert("lens", frame=f)


KEY_E, BOX_E, GRAZE_E, INNER_E, RIM_E = 170, 9.0, 10, 0.45, 190
if args.mode == "intro":
    # straight push-in that settles, the light box fading on at the start
    cam_key(1, (0, -14.0, 1.3), 2.5, 40)
    cam_key(26, (0, -9.5, 1.3), 2.45, 40)
    cam_key(80, (0, -6.4, 1.2), 1.65, 45)
    cam_key(160, (0, -4.3, TOP + 0.36), 1.42, 50)
    cam_key(INTRO_LEN, END["loc"], END["tz"], END["lens"])
    for f, k in [(1, 0.03), (10, 0.12), (36, 1.0)]:
        key.data.energy, panel_strength.default_value, graze.data.energy = KEY_E * k, BOX_E * k, GRAZE_E * k
        inner_glow.default_value = INNER_E * k
        inner_glow.keyframe_insert("default_value", frame=f)
        rimL.data.energy = RIM_E * k * k        # the rock reveals a little later than the box
        rimL.data.keyframe_insert("energy", frame=f)
        key.data.keyframe_insert("energy", frame=f)
        panel_strength.keyframe_insert("default_value", frame=f)
        graze.data.keyframe_insert("energy", frame=f)
    glint_sweep(165, 215)
    frames = args.frames or [1, INTRO_LEN]
else:
    # the held last frame, with the glint passing; first and last frames match
    cam_key(1, END["loc"], END["tz"], END["lens"])
    key.data.energy, panel_strength.default_value, graze.data.energy = KEY_E, BOX_E, GRAZE_E
    inner_glow.default_value = INNER_E
    rimL.data.energy = RIM_E
    glint_sweep(12, 84)
    frames = args.frames or [1, LOOP_LEN]

# ---------------------------------------------------------------- render
world = bpy.data.worlds.new("w")
world.color = (0, 0, 0)
scene.world = world
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = args.samples
scene.cycles.use_denoising = True
scene.cycles.max_bounces = 6
scene.render.use_persistent_data = True
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Punchy"
scene.render.resolution_x, scene.render.resolution_y = args.res
scene.render.fps = 24
scene.render.image_settings.file_format = "PNG"
scene.frame_start, scene.frame_end = frames
os.makedirs(args.out, exist_ok=True)
if args.still is not None:
    scene.frame_set(args.still)
    scene.render.filepath = os.path.join(args.out, f"{args.mode}_{args.still:04d}.png")
    bpy.ops.render.render(write_still=True)
else:
    scene.render.filepath = os.path.join(args.out, f"{args.mode}_")
    bpy.ops.render.render(animation=True)
