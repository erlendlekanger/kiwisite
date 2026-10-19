"""Shared Blender (bpy) studio for FOMOHUB renders: palette, materials, lights, camera, render."""
import bpy, math, os, json
from mathutils import Vector

# fomo house palette (sRGB hex -> linear)
def lin(hexs):
    h = hexs.lstrip('#'); r, g, b = (int(h[i:i+2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (f(r), f(g), f(b), 1.0)

PAL = {
    'ivory': '#EAEDFF', 'navy': '#0b0a1f', 'ink': '#060510', 'blue': '#516af6', 'violet': '#606af7',
    'orange': '#ff622e', 'green': '#21c95e', 'gold': '#ffc74f', 'gold2': '#e1b048', 'silver': '#cbd0eb',
    'bronze': '#c27a3a', 'white': '#f7f7f7',
}

def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    sc.cycles.max_bounces = 8
    sc.cycles.glossy_bounces = 6
    sc.cycles.transmission_bounces = 10
    sc.cycles.transparent_max_bounces = 12
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.blur_glossy = 0.6
    sc.render.film_transparent = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.image_settings.compression = 60
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.resolution_percentage = 100
    world = bpy.data.worlds.new('W'); sc.world = world
    world.use_nodes = True
    nt = world.node_tree; bg = nt.nodes['Background']
    # soft studio gradient: dark below, light above, so glossy surfaces get a gradient reflection
    tc = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ'); ramp = nt.nodes.new('ShaderNodeValToRGB')
    mr = nt.nodes.new('ShaderNodeMath'); mr.operation = 'MULTIPLY_ADD'; mr.inputs[1].default_value = 0.5; mr.inputs[2].default_value = 0.5
    ramp.color_ramp.elements[0].color = (0.02, 0.02, 0.05, 1); ramp.color_ramp.elements[1].color = (0.7, 0.75, 0.95, 1)
    ramp.color_ramp.elements[0].position = 0.35; ramp.color_ramp.elements[1].position = 0.95
    nt.links.new(tc.outputs['Generated'], sep.inputs[0]); nt.links.new(sep.outputs['Z'], mr.inputs[0])
    nt.links.new(mr.outputs[0], ramp.inputs[0]); nt.links.new(ramp.outputs['Color'], bg.inputs[0])
    bg.inputs[1].default_value = 0.6
    return sc

def mat(name, color, rough=0.25, coat=0.3, metal=0.0, sss=0.0, emit=None, trans=0.0, ior=1.45, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; p = nt.nodes['Principled BSDF']
    col = lin(color) if isinstance(color, str) else color
    p.inputs['Base Color'].default_value = col
    p.inputs['Roughness'].default_value = rough
    p.inputs['Metallic'].default_value = metal
    p.inputs['IOR'].default_value = ior
    p.inputs['Coat Weight'].default_value = coat
    p.inputs['Coat Roughness'].default_value = 0.08
    p.inputs['Specular IOR Level'].default_value = spec
    if sss:
        p.inputs['Subsurface Weight'].default_value = sss
        p.inputs['Subsurface Radius'].default_value = (0.08, 0.06, 0.05)
        p.inputs['Subsurface Scale'].default_value = 0.3
    if trans:
        p.inputs['Transmission Weight'].default_value = trans
    if emit:
        p.inputs['Emission Color'].default_value = lin(emit)
        p.inputs['Emission Strength'].default_value = 1.5
    return m

def speckle(m, strength=0.015, scale=120):
    """tiny surface grain like the Axo renders (very subtle on light plastic)"""
    nt = m.node_tree; p = nt.nodes['Principled BSDF']
    noise = nt.nodes.new('ShaderNodeTexNoise'); noise.inputs['Scale'].default_value = scale
    noise.inputs['Detail'].default_value = 3
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = strength
    nt.links.new(noise.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], p.inputs['Normal'])
    return m

def smooth(ob, angle=50):
    ob.select_set(True); bpy.context.view_layer.objects.active = ob
    bpy.ops.object.shade_smooth_by_angle(angle=math.radians(angle))
    ob.select_set(False)

def add_mod_bevel(ob, width=0.03, segments=5):
    b = ob.modifiers.new('bevel', 'BEVEL'); b.width = width; b.segments = segments; b.limit_method = 'ANGLE'; b.angle_limit = math.radians(40)
    return b

def add_subsurf(ob, levels=2):
    s = ob.modifiers.new('sub', 'SUBSURF'); s.levels = levels; s.render_levels = levels
    return s

def link(ob):
    bpy.context.scene.collection.objects.link(ob); return ob

def prim(kind, name, loc=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), **kw):
    op = {'cube': bpy.ops.mesh.primitive_cube_add, 'sphere': bpy.ops.mesh.primitive_uv_sphere_add,
          'cyl': bpy.ops.mesh.primitive_cylinder_add, 'cone': bpy.ops.mesh.primitive_cone_add,
          'torus': bpy.ops.mesh.primitive_torus_add, 'plane': bpy.ops.mesh.primitive_plane_add}[kind]
    op(location=loc, rotation=rot, **kw)
    ob = bpy.context.active_object; ob.name = name; ob.scale = scale
    return ob

def set_mat(ob, m):
    ob.data.materials.clear(); ob.data.materials.append(m)

def studio(cam_loc=(0, -7.5, 3.2), cam_target=(0, 0, 0.3), lens=85, key=1200, fill=350, rim=500, floor_z=0.0, floor=True):
    """Three soft area lights + a shadow-catching floor + camera aimed at the target."""
    sc = bpy.context.scene
    def area(name, loc, target, energy, size, color=(1, 1, 1)):
        d = bpy.data.lights.new(name, 'AREA'); d.energy = energy; d.size = size; d.color = color
        d.shape = 'RECTANGLE'; d.size_y = size * 0.75
        o = bpy.data.objects.new(name, d); link(o); o.location = loc
        look_at(o, target); return o
    area('key', (-4.5, -4.5, 7.0), cam_target, key, 5.0, (1.0, 0.97, 0.93))
    area('fill', (6.0, -4.0, 3.0), cam_target, fill, 6.0, (0.85, 0.9, 1.0))
    area('rim', (2.0, 5.0, 6.0), cam_target, rim, 3.0, (0.9, 0.93, 1.0))
    if floor:
        p = prim('plane', 'floor', loc=(0, 0, floor_z), scale=(40, 40, 1))
        p.is_shadow_catcher = True
        p.visible_glossy = False; p.visible_diffuse = False
    c = bpy.data.cameras.new('cam'); c.lens = lens; c.sensor_width = 36
    co = bpy.data.objects.new('cam', c); link(co); co.location = cam_loc
    (look_down if abs(cam_loc[2]) > 2.5 * math.hypot(cam_loc[0], cam_loc[1]) else look_at)(co, cam_target)
    sc.camera = co
    return co

def look_down(o, target):
    """aim a camera that hangs above the scene, keeping world +Y as its up (no roll)"""
    d = (Vector(target) - o.location).normalized()
    ax = math.asin(max(-1, min(1, d.y))); ay = math.asin(max(-1, min(1, -d.x / max(1e-6, math.cos(ax)))))
    o.rotation_euler = (ax, ay, 0)

def look_at(o, target):
    d = Vector(target) - o.location
    o.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()

def render(path, w=900, h=900, samples=192):
    sc = bpy.context.scene
    sc.render.resolution_x = w; sc.render.resolution_y = h
    sc.cycles.samples = samples
    sc.cycles.adaptive_threshold = 0.02
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print('rendered', path)

def proj(co):
    """world point -> normalized render coords (x right, y down)"""
    from bpy_extras.object_utils import world_to_camera_view
    sc = bpy.context.scene
    bpy.context.view_layer.update()
    v = world_to_camera_view(sc, sc.camera, Vector(co))
    return [round(v.x, 5), round(1 - v.y, 5)]
