"""  """

import math
import mathutils

import bpy

from . import dsq_file
from . import dts_types
from . import util


def get_free_name(name, taken):
    if name not in taken:
        return name

    suffix = 1

    while True:
        name_try = name + "." + str(suffix)

        if name_try not in taken:
            return name_try

        suffix += 1


def load(operator, context, filepath, debug_report=False):
    dsq = dsq_file.DsqFile()

    with open(filepath, "rb") as fd:
        dsq.read(fd)

    if debug_report:
        with open(filepath + ".txt", "w") as fd:
            dsq.write_dump(fd)

    print("Resolving nodes...")

    found_obs = {}

    # Find all our candidate nodes
    # DSQ is case-insensitive, that's why we can't just [] lookup
    for ob in context.scene.objects:
        if ob.type in ("EMPTY", "ARMATURE"):
            name = ob.name.lower()

            if name in found_obs:
                print(
                    "Warning: Nodes with varying capitalization found ('{}', '{}'), ignoring second"
                    .format(found_obs[name].name, ob.name))
                continue

            found_obs[name] = ob

    nodes = [None] * len(dsq.nodes)
    node_missing = []

    # Now associate DSQ node indices with Blender objects
    for index, name in enumerate(dsq.nodes):
        lower = name.lower()

        if lower in found_obs:
            nodes[index] = found_obs[lower]
        else:
            node_missing.append(name)

    if node_missing:
        return util.fail(
            operator,
            "The following nodes from the DSQ file could not be found in your scene:\n"
            + ", ".join(node_missing))

    # Now, find all the existing sequence names so we can rename duplicates
    # Also find out where the last user-defined animation data is
    last_frame = 1
    scene_sequences = set()

    for marker in context.scene.timeline_markers:
        last_frame = max(last_frame, int(math.ceil(marker.frame + 10)))

        if ":" not in marker.name:
            continue

        name, what = marker.name.rsplit(":", 1)
        scene_sequences.add(name)

    for action in bpy.data.actions:
        last_frame = max(last_frame, int(math.ceil(action.frame_range[1] + 10)))

    if "Sequences" in bpy.data.texts:
        for line in bpy.data.texts["Sequences"].as_string().split("\n"):
            line = line.strip()

            if not line or line == "strict" or ":" not in line:
                continue

            name, flags = line.split(":", 1)
            scene_sequences.add(name)

    sequences_text = []
    reference_frame = util.find_reference(context.scene)

    # Create Blender keyframes and markers for each sequence
    for seq in dsq.sequences:
        name = get_free_name(seq.name, scene_sequences)
        print("found seq", seq.name, "to", name)

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
            map(lambda p: p[0],
                filter(lambda p: p[1], zip(nodes, seq.rotationMatters))))
        nodesTranslation = tuple(
            map(lambda p: p[0],
                filter(lambda p: p[1], zip(nodes, seq.translationMatters))))
        nodesScale = tuple(
            map(lambda p: p[0],
                filter(lambda p: p[1], zip(nodes, seq.scaleMatters))))

        step = 1

        for mattersIndex, ob in enumerate(nodesTranslation):
            curves = util.ob_location_curves(ob)

            for frameIndex in range(seq.numKeyframes):
                vec = dsq.translations[seq.baseTranslation +
                                       mattersIndex * seq.numKeyframes +
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
                    key.co = (last_frame + frameIndex * step,
                              vec[curve.array_index])

        for mattersIndex, ob in enumerate(nodesRotation):
            mode, curves = util.ob_rotation_curves(ob)

            for frameIndex in range(seq.numKeyframes):
                rot = dsq.rotations[seq.baseRotation +
                                    mattersIndex * seq.numKeyframes +
                                    frameIndex]
                if seq.flags & dts_types.Sequence.Blend:
                    if reference_frame is None:
                        return util.fail(
                            operator,
                            "Missing 'reference' marker for blend animation '{}'"
                            .format(name))
                    ref_rot = mathutils.Quaternion(util.evaluate_all(curves, reference_frame))
                    rot = ref_rot * rot
                if mode == 'AXIS_ANGLE':
                    rot = rot.to_axis_angle()
                elif mode != 'QUATERNION':
                    rot = rot.to_euler(mode)

                for curve in curves:
                    curve.keyframe_points.add(1)
                    key = curve.keyframe_points[-1]
                    key.interpolation = "LINEAR"
                    key.co = (last_frame + frameIndex * step,
                              rot[curve.array_index])

        for mattersIndex, ob in enumerate(nodesScale):
            curves = util.ob_scale_curves(ob)

            for frameIndex in range(seq.numKeyframes):
                index = seq.baseScale + mattersIndex * seq.numKeyframes + frameIndex

                if seq.flags & dts_types.Sequence.UniformScale:
                    s = dsq.uniform_scales[index]
                    scale = s, s, s
                elif seq.flags & dts_types.Sequence.AlignedScale:
                    scale = dsq.aligned_scales[index]
                elif seq.flags & dts_types.Sequence.ArbitraryScale:
                    print("Warning: Arbitrary scale animation not implemented")
                    break
                else:
                    print("Warning: Invalid scale flags found in sequence")
                    break

                for curve in curves:
                    curve.keyframe_points.add(1)
                    key = curve.keyframe_points[-1]
                    key.interpolation = "LINEAR"
                    key.co = (last_frame + frameIndex * step,
                              scale[curve.array_index])

        context.scene.timeline_markers.new(name + ":start", last_frame)
        context.scene.timeline_markers.new(name + ":end",
                                           last_frame + seq.numKeyframes)

        last_frame += seq.numKeyframes + 10

    if "Sequences" in bpy.data.texts:
        sequences_buf = bpy.data.texts["Sequences"]
    else:
        sequences_buf = bpy.data.texts.new("Sequences")

    if not sequences_buf.as_string():
        sequences_buf.from_string("\n".join(sequences_text))
    else:
        sequences_buf.from_string(sequences_buf.as_string() + "\n" +
                                  "\n".join(sequences_text))

    return {"FINISHED"}
