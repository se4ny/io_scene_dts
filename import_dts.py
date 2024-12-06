"""  """

import itertools
import mathutils
import os

import bpy
from bpy_extras import io_utils

from . import dts_shape
from . import dts_types
from . import util
from . import write_report


def grouper(iterable, n, fillvalue=None):
    """  
    
    :param iterable:
    :param n:
    :param fillvalue:

    :meta public:
    """
    "Collect data into fixed-length chunks or blocks"
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx"
    args = [iter(iterable)] * n
    return itertools.zip_longest(*args, fillvalue=fillvalue)


def dedup_name(group, name):
    """  
    
    :param group:
    :param name:

    :meta public:
    """
    if name not in group:
        return name

    for suffix in itertools.count(2):
        new_name = name + "#" + str(suffix)

        if new_name not in group:
            return new_name


def import_material(color_source, dmat: dts_types.Material, filepath: str) -> bpy.types.Material:
    """ TODO
    
    :param color_source:
    :param dmat:
    :param filepath:

    :meta public:
    """
    bmat = bpy.data.materials.new(dedup_name(bpy.data.materials, dmat.name))
    bmat.diffuse_intensity = 1

    texname = util.resolve_texture(filepath, dmat.name)

    if texname is not None:
        try:
            teximg = bpy.data.images.load(texname)
        except:
            print("Cannot load image", texname)

        texslot = bmat.texture_slots.add()
        texslot.use_map_alpha = True
        tex = texslot.texture = bpy.data.textures.new(dmat.name, "IMAGE")
        tex.image = teximg

        # Try to figure out a diffuse color for solid shading
        if teximg.size[0] <= 16 and teximg.size[1] <= 16:
            if teximg.use_alpha:
                pixels = grouper(teximg.pixels, 4)
            else:
                pixels = grouper(teximg.pixels, 3)

            color = pixels.__next__()

            for other in pixels:
                if other != color:
                    break
            else:
                bmat.diffuse_color = color[:3]
    elif dmat.name.lower() in util.default_materials:
        bmat.diffuse_color = util.default_materials[dmat.name.lower()]
    else:  # give it a random color
        bmat.diffuse_color = color_source.__next__()

    if dmat.flags & dts_types.Material.SelfIlluminating:
        bmat.use_shadeless = True
    if dmat.flags & dts_types.Material.Translucent:
        bmat.use_transparency = True

    if dmat.flags & dts_types.Material.Additive:
        bmat.torque_props.blend_mode = "ADDITIVE"
    elif dmat.flags & dts_types.Material.Subtractive:
        bmat.torque_props.blend_mode = "SUBTRACTIVE"
    else:
        bmat.torque_props.blend_mode = "NONE"

    if dmat.flags & dts_types.Material.SWrap:
        bmat.torque_props.s_wrap = True
    if dmat.flags & dts_types.Material.TWrap:
        bmat.torque_props.t_wraps = True
    if dmat.flags & dts_types.Material.IFLMaterial:
        bmat.torque_props.use_ifl = True

    # TODO: MipMapZeroBorder, IFLFrame, DetailMap, BumpMap, ReflectanceMap
    # AuxilaryMask?

    return bmat


class index_pass:

    def __getitem__(self, item):
        return item


def create_bmesh(dmesh: dts_types.Mesh, materials: dts_types.Material, shape: dts_shape.Shape) -> bpy.types.Mesh:
    """ TODO
    
    :param dmesh:
    :param materials:
    :param shape:

    :meta public:
    """
    me = bpy.data.meshes.new("Mesh")

    # TODO: This code doesn't generate a proper mesh.

    faces = []
    material_indices = {}

    indices_pass = index_pass()

    for prim in dmesh.primitives:
        if prim.type & dts_types.Primitive.Indexed:
            indices = dmesh.indices
        else:
            indices = indices_pass

        dmat: None | dts_types.Material = None

        if False and not (prim.type & dts_types.Primitive.NoMaterial):
            dmat = shape.materials[prim.type & dts_types.Primitive.MaterialMask]

            if dmat not in material_indices:
                material_indices[dmat] = len(me.materials)
                me.materials.append(materials[dmat])

        if prim.type & dts_types.Primitive.Strip:
            even = True
            for i in range(prim.firstElement + 2,
                           prim.firstElement + prim.numElements):
                if even:
                    faces.append(
                        ((indices[i], indices[i - 1], indices[i - 2]), dmat))
                else:
                    faces.append(
                        ((indices[i - 2], indices[i - 1], indices[i]), dmat))
                even = not even
        elif prim.type & dts_types.Primitive.Fan:
            even = True
            for i in range(prim.firstElement + 2,
                           prim.firstElement + prim.numElements):
                if even:
                    faces.append(
                        ((indices[i], indices[i - 1], indices[0]), dmat))
                else:
                    faces.append(
                        ((indices[0], indices[i - 1], indices[i]), dmat))
                even = not even
        else:  # Default to Triangle Lists (prim.type & Primitive.Triangles)
            for i in range(prim.firstElement + 2,
                           prim.firstElement + prim.numElements, 3):
                faces.append(
                    ((indices[i], indices[i - 1], indices[i - 2]), dmat))

    me.vertices.add(len(dmesh.verts))
    me.vertices.foreach_set("co", io_utils.unpack_list(dmesh.verts))
    me.vertices.foreach_set("normal", io_utils.unpack_list(dmesh.normals))

    me.polygons.add(len(faces))
    me.loops.add(len(faces) * 3)

    # TODO: Crashes Blender.
    if False:
        me.uv_layers.new()
        uvs = me.uv_layers[0]

    for i, ((verts, dmat), poly) in enumerate(zip(faces, me.polygons)):
        poly.use_smooth = True  # DTS geometry is always smooth shaded
        # poly.loop_total = 3
        poly.loop_start = i * 3

        if False:
            if dmat:
                poly.material_index = material_indices[dmat]

        for j, index in zip(poly.loop_indices, verts):
            me.loops[j].vertex_index = index
            if False:
                uv = dmesh.tverts[index]
                uvs.data[j].uv = (uv.x, 1 - uv.y)

    me.validate(verbose=True)
    me.update()

    return me


def file_base_name(filepath: str) -> str:
    """  
    
    :param filepath:

    :meta public:
    """
    return os.path.basename(filepath).rsplit(".", 1)[0]


def insert_reference(frame, shape_nodes: list[bpy.types.Object]):
    """  
    
    :param frame:
    :param shape_nodes:

    :meta public:
    """
    for node in shape_nodes:
        ob = node.bl_ob

        curves = util.ob_location_curves(ob)
        for curve in curves:
            curve.keyframe_points.add(1)
            key = curve.keyframe_points[-1]
            key.interpolation = "LINEAR"
            key.co = (frame, ob.location[curve.array_index])

        curves = util.ob_scale_curves(ob)
        for curve in curves:
            curve.keyframe_points.add(1)
            key = curve.keyframe_points[-1]
            key.interpolation = "LINEAR"
            key.co = (frame, ob.scale[curve.array_index])

        _, curves = util.ob_rotation_curves(ob)
        rot = util.ob_rotation_data(ob)
        for curve in curves:
            curve.keyframe_points.add(1)
            key = curve.keyframe_points[-1]
            key.interpolation = "LINEAR"
            key.co = (frame, rot[curve.array_index])


def load(operator: bpy.types.Operator,
         context: bpy.types.Context,
         filepath: str,
         reference_keyframe: bool=True,
         import_sequences: bool=True,
         use_armature: bool=False,
         debug_report: bool=False) -> None:
    """  
    
    :param operator:
    :param context:
    :param filepath:
    :param reference_keyframe:
    :param import_sequences:
    :param use_armature:
    :param debug_report:

    :meta public:
    """
    shape = dts_shape.Shape()

    with open(filepath, "rb") as shapefile:
        shape.load(shapefile)

    if debug_report:
        write_report.write_debug_report(filepath + ".txt", shape)
        with open(filepath + ".pass.dts", "wb") as fd:
            shape.save(fd)

    # Create a Blender material for each DTS material
    materials = {}

    # BUG: Blender requires alpha as well.
    color_source = util.get_rgb_colors()

    # TODO: Disabled for now, because material function needs to be updated.
    if False:
        for dmat in shape.materials:
            materials[dmat] = import_material(color_source, dmat, filepath)

    # Now assign IFL material properties where needed
    # NOTE: Included for legacy reasons.
    for ifl in shape.iflmaterials:
        mat = materials[shape.materials[ifl.slot]]
        assert mat.torque_props.use_ifl == True
        mat.torque_props.ifl_name = shape.names[ifl.name]

    # First load all the nodes into armatures
    lod_by_mesh = {}

    for lod in shape.detail_levels:
        lod_by_mesh[lod.objectDetail] = lod

    node_obs = []
    node_obs_val = {}

    if use_armature:
        root_arm = bpy.data.armatures.new(file_base_name(filepath))
        root_ob = bpy.data.objects.new(root_arm.name, root_arm)
        root_ob.show_in_front = True

        context.scene.collection.objects.link(root_ob)
        context.scene.collection.objects.active = root_ob

        # Calculate armature-space matrix, head and tail for each node
        for i, node in enumerate(shape.nodes):
            node.mat = shape.default_rotations[i].to_matrix()
            node.mat = mathutils.Matrix.Translation(
                shape.default_translations[i]) * node.mat.to_4x4()
            if node.parent != -1:
                node.mat = shape.nodes[node.parent].mat * node.mat
            # node.head = node.mat.to_translation()
            # node.tail = node.head + Vector((0, 0, 0.25))
            # node.tail = node.mat.to_translation()
            # node.head = node.tail - Vector((0, 0, 0.25))

        bpy.ops.object.mode_set(mode='EDIT')

        edit_bone_table = []
        bone_names = []

        for i, node in enumerate(shape.nodes):
            bone = root_arm.edit_bones.new(shape.names[node.name])
            # bone.use_connect = True
            # bone.head = node.head
            # bone.tail = node.tail
            bone.head = (0, 0, -0.25)
            bone.tail = (0, 0, 0)

            if node.parent != -1:
                bone.parent = edit_bone_table[node.parent]

            bone.matrix = node.mat
            bone["nodeIndex"] = i

            edit_bone_table.append(bone)
            bone_names.append(bone.name)

        bpy.ops.object.mode_set(mode='OBJECT')
    else:
        if reference_keyframe:
            reference_marker = context.scene.timeline_markers.get("reference")
            if reference_marker is None:
                reference_frame = 0
                context.scene.timeline_markers.new("reference", frame=reference_frame)
            else:
                reference_frame = reference_marker.frame
        else:
            reference_frame = None

        # Create an empty for every node
        for i, node in enumerate(shape.nodes):
            ob = bpy.data.objects.new(
                dedup_name(bpy.data.objects, shape.names[node.name]), None)
            node.bl_ob = ob
            ob["nodeIndex"] = i
            ob.empty_display_type = "SINGLE_ARROW"
            ob.empty_display_size = 0.5

            if node.parent != -1:
                ob.parent = node_obs[node.parent]

            ob.location = shape.default_translations[i]
            ob.rotation_mode = "QUATERNION"
            ob.rotation_quaternion = shape.default_rotations[i]
            if shape.names[
                    node.
                    name] == "__auto_root__" and ob.rotation_quaternion.magnitude == 0:
                ob.rotation_quaternion = (1, 0, 0, 0)

            context.scene.collection.objects.link(ob)
            node_obs.append(ob)
            node_obs_val[node] = ob

        if reference_keyframe:
            insert_reference(reference_frame, shape.nodes)

    # Try animation?
    if import_sequences:
        globalToolIndex = 10
        fps = context.scene.render.fps

        sequences_text = []

        for seq in shape.sequences:
            name = shape.names[seq.nameIndex]
            print("Importing sequence", name)

            flags = []
            flags.append("priority {}".format(seq.priority))

            if seq.flags & dts_types.Sequence.Cyclic:
                flags.append("cyclic")

            if seq.flags & dts_types.Sequence.Blend:
                flags.append("blend")

            flags.append("duration {}".format(seq.duration))

            if flags:
                sequences_text.append(name + ": " + ", ".join(flags))

            nodesRotation = tuple(
                map(
                    lambda p: p[0],
                    filter(lambda p: p[1], zip(shape.nodes,
                                               seq.rotationMatters))))
            nodesTranslation = tuple(
                map(
                    lambda p: p[0],
                    filter(lambda p: p[1],
                           zip(shape.nodes, seq.translationMatters))))
            nodesScale = tuple(
                map(lambda p: p[0],
                    filter(lambda p: p[1], zip(shape.nodes,
                                               seq.scaleMatters))))

            step = 1

            for mattersIndex, node in enumerate(nodesTranslation):
                ob = node_obs_val[node]
                curves = util.ob_location_curves(ob)

                for frameIndex in range(seq.numKeyframes):
                    vec = shape.node_translations[seq.baseTranslation +
                                                  mattersIndex *
                                                  seq.numKeyframes +
                                                  frameIndex]
                    if seq.flags & dts_types.Sequence.Blend:
                        if reference_frame is None:
                            return util.fail(
                                operator,
                                "Missing 'reference' marker for blend animation '{}'"
                                .format(name))
                        ref_vec = mathutils.Vector(util.evaluate_all(curves, reference_frame))
                        vec = ref_vec + vec

                    for curve in curves:
                        curve.keyframe_points.add(1)
                        key = curve.keyframe_points[-1]
                        key.interpolation = "LINEAR"
                        key.co = (globalToolIndex + frameIndex * step,
                                  vec[curve.array_index])

            for mattersIndex, node in enumerate(nodesRotation):
                ob = node_obs_val[node]
                mode, curves = util.ob_rotation_curves(ob)

                for frameIndex in range(seq.numKeyframes):
                    rot = shape.node_rotations[seq.baseRotation +
                                               mattersIndex * seq.numKeyframes
                                               + frameIndex]
                    if seq.flags & dts_types.Sequence.Blend:
                        if reference_frame is None:
                            return util.fail(
                                operator,
                                "Missing 'reference' marker for blend animation '{}'"
                                .format(name))
                        ref_rot = mathutils.Quaternion(
                            util.evaluate_all(curves, reference_frame))
                        rot = ref_rot * rot
                    if mode == 'AXIS_ANGLE':
                        rot = rot.to_axis_angle()
                    elif mode != 'QUATERNION':
                        rot = rot.to_euler(mode)

                    for curve in curves:
                        curve.keyframe_points.add(1)
                        key = curve.keyframe_points[-1]
                        key.interpolation = "LINEAR"
                        key.co = (globalToolIndex + frameIndex * step,
                                  rot[curve.array_index])

            for mattersIndex, node in enumerate(nodesScale):
                ob = node_obs_val[node]
                curves = util.ob_scale_curves(ob)

                for frameIndex in range(seq.numKeyframes):
                    index = seq.baseScale + mattersIndex * seq.numKeyframes + frameIndex
                    vec = shape.node_translations[seq.baseTranslation +
                                                  mattersIndex *
                                                  seq.numKeyframes +
                                                  frameIndex]

                    if seq.flags & dts_types.Sequence.UniformScale:
                        s = shape.node_uniform_scales[index]
                        vec = (s, s, s)
                    elif seq.flags & dts_types.Sequence.AlignedScale:
                        vec = shape.node_aligned_scales[index]
                    elif seq.flags & dts_types.Sequence.ArbitraryScale:
                        print(
                            "Warning: Arbitrary scale animation not implemented"
                        )
                        break
                    else:
                        print("Warning: Invalid scale flags found in sequence")
                        break

                    for curve in curves:
                        curve.keyframe_points.add(1)
                        key = curve.keyframe_points[-1]
                        key.interpolation = "LINEAR"
                        key.co = (globalToolIndex + frameIndex * step,
                                  vec[curve.array_index])

            # Insert a reference frame immediately before the animation
            # insert_reference(globalToolIndex - 2, shape.nodes)

            context.scene.timeline_markers.new(name + ":start",
                                               globalToolIndex)
            context.scene.timeline_markers.new(
                name + ":end", globalToolIndex + seq.numKeyframes * step - 1)
            globalToolIndex += seq.numKeyframes * step + 30

        if "Sequences" in bpy.data.texts:
            sequences_buf = bpy.data.texts["Sequences"]
        else:
            sequences_buf = bpy.data.texts.new("Sequences")

        sequences_buf.from_string("\n".join(sequences_text))

    # Then put objects in the armatures
    for obj in shape.objects:
        if obj.node == -1:
            print('Warning: Object {} is not attached to a node, ignoring'.
                  format(shape.names[obj.name]))
            continue

        for meshIndex in range(obj.numMeshes):
            mesh = shape.meshes[obj.firstMesh + meshIndex]
            mtype = mesh.type

            if mtype == dts_types.Mesh.NullType:
                continue

            if mtype != dts_types.Mesh.StandardType and mtype != dts_types.Mesh.SkinType:
                print(
                    'Warning: Mesh #{} of object {} is of unsupported type {}, ignoring'
                    .format(meshIndex + 1, mtype, shape.names[obj.name]))
                continue

            bmesh = create_bmesh(mesh, materials, shape)
            bobj = bpy.data.objects.new(
                dedup_name(bpy.data.objects, shape.names[obj.name]), bmesh)
            context.scene.collection.objects.link(bobj)

            add_vertex_groups(mesh, bobj, shape)

            if use_armature:
                bobj.parent = root_ob
                bobj.parent_bone = bone_names[obj.node]
                bobj.parent_type = 'BONE'
                bobj.matrix_world = shape.nodes[obj.node].mat

                if mtype == dts_types.Mesh.SkinType:
                    modifier = bobj.modifiers.new('Armature', 'ARMATURE')
                    modifier.object = root_ob
            else:
                bobj.parent = node_obs[obj.node]

            lod_name = shape.names[lod_by_mesh[meshIndex].name]

            if lod_name not in bpy.data.collections:
                bpy.data.collections.new(lod_name)

            bpy.data.collections[lod_name].objects.link(bobj)

    # Import a bounds mesh
    me = bpy.data.meshes.new("Mesh")
    me.vertices.add(8)
    me.vertices[0].co = (shape.bounds.min.x, shape.bounds.min.y, shape.bounds.min.z)
    me.vertices[1].co = (shape.bounds.max.x, shape.bounds.min.y, shape.bounds.min.z)
    me.vertices[2].co = (shape.bounds.max.x, shape.bounds.max.y, shape.bounds.min.z)
    me.vertices[3].co = (shape.bounds.min.x, shape.bounds.max.y, shape.bounds.min.z)
    me.vertices[4].co = (shape.bounds.min.x, shape.bounds.min.y, shape.bounds.max.z)
    me.vertices[5].co = (shape.bounds.max.x, shape.bounds.min.y, shape.bounds.max.z)
    me.vertices[6].co = (shape.bounds.max.x, shape.bounds.max.y, shape.bounds.max.z)
    me.vertices[7].co = (shape.bounds.min.x, shape.bounds.max.y, shape.bounds.max.z)
    me.validate()
    me.update()
    ob = bpy.data.objects.new("bounds", me)
    ob.display_type = 'BOUNDS'
    context.scene.collection.objects.link(ob)

    return {"FINISHED"}


def add_vertex_groups(mesh: dts_types.Mesh, ob: bpy.types.Object, shape: dts_shape.Shape) -> None:
    """ 
    
    :param mesh:
    :param ob:
    :param shape:

    :meta public:
    """
    for node, _ in mesh.bones:
        # TODO: Handle initial_transform
        ob.vertex_groups.new(shape.names[shape.nodes[node].name])

    for vertex, bone, weight in mesh.influences:
        ob.vertex_groups[bone].add((vertex, ), weight, 'REPLACE')
