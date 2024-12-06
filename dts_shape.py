"""  """

import io
import mathutils
import struct

from . import dts_utils
from . import dts_stream
from . import dts_types


class Shape(object):
    """  """
    def __init__(self) -> None:
        self.nodes: list[dts_types.Node] = []
        self.objects: list[dts_types.Object] = []
        self.decals = []
        self.subshapes: list[dts_types.Subshape] = []
        self.iflmaterials: list[dts_types.IflMaterial] = []
        self.materials: list[dts_types.Material] = []
        self.default_rotations: list[None | mathutils.Quaternion] = []
        self.default_translations: list[None | mathutils.Vector] = []
        self.node_rotations: list[mathutils.Quaternion] = []
        self.node_translations: list[mathutils.Vector] = []
        self.node_uniform_scales: list[float] = []
        self.node_aligned_scales: list[mathutils.Vector] = []
        self.node_arbitrary_scale_factors: list[mathutils.Vector] = []
        self.node_arbitrary_scale_rots: list[mathutils.Quaternion] = []
        self.ground_translations: list[mathutils.Vector] = []
        self.ground_rotations: list[mathutils.Quaternion] = []
        self.objectstates: list[dts_types.ObjectState] = []
        self.decalstates: list[int] = []
        self.triggers: list[dts_types.Trigger] = []
        self.detail_levels: list[dts_types.DetailLevel] = []
        self.meshes: list[dts_types.Mesh] = []
        self.sequences: list[dts_types.Sequence] = []
        self.names: list[str] = []
        self._names_lookup: dict[str, int] = {}

        self.smallest_size: float = 0.0
        self.smallest_detail_level: int = 0
        self.radius: float = 0.0
        self.radius_tube: float = 0.0
        self.center: mathutils.Vector = mathutils.Vector()
        self.bounds: dts_utils.Box = dts_utils.Box(mathutils.Vector(), mathutils.Vector())

    def name(self, string: str) -> int:
        index = self._names_lookup.get(string.lower())

        if index == None:
            index = len(self.names)
            self.names.append(string)
            self._names_lookup[string.lower()] = index

        return index

    def name_resolve(self, string: str) -> tuple[int, str]:
        index = self.name(string)
        return (index, self.names[index])

    def get_world_mat(self, nodeid: int) -> mathutils.Matrix:
        matrix = mathutils.Matrix()

        while nodeid != -1:
            cur = mathutils.Matrix.Translation(
                self.default_translations[nodeid]
            ) * self.default_rotations[nodeid].to_matrix()
            matrix = cur * matrix
            nodeid = self.nodes[nodeid].parent

        return matrix

    def verify(self):
        """  
        
        :raises :py:`AssertionError`:
        """
        assert self.detail_levels
        assert self.subshapes
        assert len(self.nodes) == len(self.default_translations)
        assert len(self.nodes) == len(self.default_rotations)
        assert len(self.objects) == len(self.objectstates)
        assert len(self.node_arbitrary_scale_factors) == len(self.node_arbitrary_scale_rots)
        assert len(self.ground_translations) == len(self.ground_rotations)

    def save(self, fd: str, dtsVersion: int=24) -> None:
        """  
        
        :raises :py:`EOFError`:
        :raises :py:`AssertionError`:
        """
        stream = dts_stream.OutStream(dtsVersion)

        # Header
        stream.write32(
            len(self.nodes),
            len(self.objects),
            len(self.decals),
            len(self.subshapes),
            len(self.iflmaterials),
            len(self.node_rotations),
            len(self.node_translations),
            len(self.node_uniform_scales),
            len(self.node_aligned_scales),
            len(self.node_arbitrary_scale_factors),
            len(self.ground_translations),
            len(self.objectstates),
            len(self.decalstates),
            len(self.triggers),
            len(self.detail_levels),
            len(self.meshes),
            len(self.names),
        )
        stream.write_float(self.smallest_size)
        stream.write32(self.smallest_detail_level)

        if dtsVersion > 24:
            # write morphs
            pass

        stream.guard(0)

        # Bounds
        stream.write_float(self.radius, self.radius_tube)
        stream.write_vec3(self.center)
        stream.write_box(self.bounds)
        stream.guard(1)

        # Nodes
        for node in self.nodes:
            node.write(stream)
        stream.guard(2)

        # Objects
        for obj in self.objects:
            obj.write(stream)
        stream.guard(3)

        # Decals
        for decal in self.decals:
            decal.write(stream)
        stream.guard(4)

        # IFL materials
        for ifl in self.iflmaterials:
            ifl.write(stream)
        stream.guard(5)

        # Subshapes
        for sub in self.subshapes:
            stream.write32(sub.firstNode)
        for sub in self.subshapes:
            stream.write32(sub.firstObject)
        for sub in self.subshapes:
            stream.write32(sub.firstDecal)
        stream.guard(6)
        for sub in self.subshapes:
            stream.write32(sub.numNodes)
        for sub in self.subshapes:
            stream.write32(sub.numObjects)
        for sub in self.subshapes:
            stream.write32(sub.numDecals)
        stream.guard(7)

        # Default translations and rotations
        assert len(self.default_rotations) == len(self.nodes)
        assert len(self.default_translations) == len(self.nodes)

        for i in range(len(self.nodes)):
            stream.write_quat(self.default_rotations[i])
            stream.write_vec3(self.default_translations[i])

        # Animation translations and rotations
        for point in self.node_translations:
            stream.write_vec3(point)
        for quat in self.node_rotations:
            stream.write_quat(quat)
        stream.guard(8)

        # Default scales
        for point in self.node_uniform_scales:
            stream.write_float(point)
        for point in self.node_aligned_scales:
            stream.write_vec3(point)
        for point in self.node_arbitrary_scale_factors:
            stream.write_vec3(point)
        # if dtsVersion >= 26:
        for quat in self.node_arbitrary_scale_rots:
            stream.write_quat(quat)
        stream.guard(9)

        # Ground transformations
        assert len(self.ground_translations) == len(self.ground_rotations)
        for point in self.ground_translations:
            self.write_vec3(point)
        for quat in self.ground_rotations:
            self.write_quat(quat)
        stream.guard(10)

        # dts_types.Object states
        for state in self.objectstates:
            state.write(stream)
        stream.guard(11)

        # Decal states
        for state in self.decalstates:
            state.write(stream)
        stream.guard(12)

        # Triggers
        for trigger in self.triggers:
            trigger.write(stream)
        stream.guard(13)

        # Detail levels
        for lod in self.detail_levels:
            lod.write(stream)
        stream.guard(14)

        # Meshes
        for mesh in self.meshes:
            mesh.write(stream)
        stream.guard()

        # Names
        for name in self.names:
            stream.write_string(name)
        stream.guard()

        # Finished with the 3-buffer section
        stream.flush(fd)

        # Sequences
        dts_stream.ws(fd, "<i", len(self.sequences))

        for seq in self.sequences:
            seq.write(fd)

        # Materials
        dts_stream.ws(fd, "b", 0x1)
        dts_stream.ws(fd, "i", len(self.materials))

        for mat in self.materials:
            if dtsVersion >= 26:
                dts_stream.ws(fd, "i", len(mat.name))
            else:
                dts_stream.ws(fd, "b", len(mat.name))

            fd.write(mat.name.encode("cp1252"))
        for mat in self.materials:
            dts_stream.ws(fd, "i", mat.flags)
        for mat in self.materials:
            dts_stream.ws(fd, "i", mat.reflectanceMap)
        for mat in self.materials:
            dts_stream.ws(fd, "i", mat.bumpMap)
        for mat in self.materials:
            dts_stream.ws(fd, "i", mat.detailMap)
        if dtsVersion == 25:
            for mat in self.materials:
                fd.write(b"\x00\x00\x00\x00")
        for mat in self.materials:
            dts_stream.ws(fd, "f", mat.detailScale)
        for mat in self.materials:
            dts_stream.ws(fd, "f", mat.reflectance)

    def load(self, buffer: io.BufferedReader) -> None:
        stream = dts_stream.InStream(buffer)

        # Header
        n_node = stream.read32()
        n_object = stream.read32()
        n_decal = stream.read32()
        n_subshape = stream.read32()
        n_ifl = stream.read32()

        if stream.dtsVersion < 22:
            n_noderotation = stream.read32()
            n_noderotation -= n_node
            n_nodetranslation = n_noderotation
            n_nodescaleuniform = 0
            n_nodescalealigned = 0
            n_nodescalearbitrary = 0
        else:
            n_noderotation = stream.read32()
            n_nodetranslation = stream.read32()
            n_nodescaleuniform = stream.read32()
            n_nodescalealigned = stream.read32()
            n_nodescalearbitrary = stream.read32()

        if stream.dtsVersion > 23:
            n_groundframe = stream.read32()
        else:
            n_groundframe = 0

        n_objectstate = stream.read32()
        n_decalstate = stream.read32()
        n_trigger = stream.read32()
        n_detaillevel = stream.read32()
        n_mesh = stream.read32()

        if stream.dtsVersion < 23:
            _ = stream.read32()

        n_name = stream.read32()
        self.smallest_size = stream.read_float()
        self.smallest_detail_level = stream.read32()
        stream.guard()

        # Misc geometry properties
        self.radius = stream.read_float()
        self.radius_tube = stream.read_float()
        self.center = stream.read_vec3()
        self.bounds = stream.read_box()
        stream.guard()

        # Primary data
        self.nodes = [dts_types.Node.read(stream) for i in range(n_node)]
        stream.guard()
        self.objects = [dts_types.Object.read(stream) for i in range(n_object)]
        stream.guard()
        self.decals = [dts_types.Decal.read(stream) for i in range(n_decal)]
        stream.guard()
        self.iflmaterials = [dts_types.IflMaterial.read(stream) for i in range(n_ifl)]
        stream.guard()

        # Subshapes
        self.subshapes = [
            dts_types.Subshape(0, 0, 0, 0, 0, 0) for i in range(n_subshape)
        ]
        for i in range(n_subshape):
            self.subshapes[i].firstNode = stream.read32()
        for i in range(n_subshape):
            self.subshapes[i].firstObject = stream.read32()
        for i in range(n_subshape):
            self.subshapes[i].firstDecal = stream.read32()
        stream.guard()
        for i in range(n_subshape):
            self.subshapes[i].numNodes = stream.read32()
        for i in range(n_subshape):
            self.subshapes[i].numObjects = stream.read32()
        for i in range(n_subshape):
            self.subshapes[i].numDecals = stream.read32()
        stream.guard()

        # MeshIndexList (obsolete data)
        if stream.dtsVersion < 16:
            for i in range(stream.read32()):
                stream.read32()

        # Default translations and rotations
        self.default_rotations = [None] * n_node
        self.default_translations = [None] * n_node

        for i in range(n_node):
            self.default_rotations[i] = stream.read_quat()
            self.default_translations[i] = stream.read_vec3()

        # Animation translations and rotations
        self.node_translations = [
            stream.read_vec3() for i in range(n_nodetranslation)
        ]
        self.node_rotations = [
            stream.read_quat() for i in range(n_noderotation)
        ]
        stream.guard()

        # Default scales
        if stream.dtsVersion > 21:
            self.node_uniform_scales = [
                stream.read_float() for i in range(n_nodescaleuniform)
            ]
            self.node_aligned_scales = [
                stream.read_vec3() for i in range(n_nodescalealigned)
            ]
            self.node_arbitrary_scale_factors = [
                stream.read_vec3() for i in range(n_nodescalearbitrary)
            ]
            self.node_arbitrary_scale_rots = [
                stream.read_quat() for i in range(n_nodescalearbitrary)
            ]
            stream.guard()
        else:
            self.node_uniform_scales = [None] * n_nodescaleuniform
            self.node_aligned_scales = [None] * n_nodescalealigned
            self.node_arbitrary_scale_factors = [None] * n_nodescalearbitrary
            self.node_arbitrary_scale_rots = [None] * n_nodescalearbitrary
        # ???
        # print(stream.dtsVersion)
        # print(stream.sequence)
        # if stream.dtsVersion > 21:
        # 	what1 = stream.read32()
        # 	what2 = stream.read32()
        # 	what3 = stream.read32()
        # 	stream.guard()

        # Ground transformations
        if stream.dtsVersion > 23:
            self.ground_translations = [
                stream.read_vec3() for i in range(n_groundframe)
            ]
            self.ground_rotations = [
                stream.read_quat() for i in range(n_groundframe)
            ]
            stream.guard()
        else:
            self.ground_translations = [None] * n_groundframe
            self.ground_rotations = [None] * n_groundframe

        # dts_types.Object states
        self.objectstates = [
            dts_types.ObjectState.read(stream) for i in range(n_objectstate)
        ]
        stream.guard()

        # Decal states
        self.decalstates = [stream.read32() for i in range(n_decalstate)]
        stream.guard()

        # Triggers
        self.triggers = [dts_types.Trigger.read(stream) for i in range(n_trigger)]
        stream.guard()

        # Detail levels
        self.detail_levels = [
            dts_types.DetailLevel.read(stream) for i in range(n_detaillevel)
        ]
        stream.guard()

        # Meshes
        self.meshes = [dts_types.Mesh.read(stream) for i in range(n_mesh)]
        stream.guard()

        # Names
        self.names = [None] * n_name
        self._names_lookup = {}

        for i in range(n_name):
            self.names[i] = stream.read_string()
            self._names_lookup[self.names[i]] = i

        stream.guard()

        self.alpha_in = [None] * n_detaillevel
        self.alpha_out = [None] * n_detaillevel

        if stream.dtsVersion >= 26:
            for i in range(n_detaillevel):
                self.alphaIn[i] = stream.read32()
            for i in range(n_detaillevel):
                self.alphaOut[i] = stream.read32()

        # Done with the tribuffer section
        n_sequence = struct.unpack("i", buffer.read(4))[0]
        self.sequences = [None] * n_sequence

        for i in range(n_sequence):
            self.sequences[i] = dts_types.Sequence.read(buffer)

        material_type = struct.unpack("b", buffer.read(1))[0]
        assert material_type == 0x1

        n_material = struct.unpack("i", buffer.read(4))[0]
        self.materials = [dts_types.Material() for i in range(n_material)]

        for i in range(n_material):
            if stream.dtsVersion >= 26:
                length = struct.unpack("i", buffer.read(4))[0]
            else:
                length = struct.unpack("B", buffer.read(1))[0]

            self.materials[i].name = buffer.read(length).decode("cp1252")

        for i in range(n_material):
            self.materials[i].flags = struct.unpack("I", buffer.read(4))[0]
        for i in range(n_material):
            self.materials[i].reflectanceMap = struct.unpack("i", buffer.read(4))[0]
        for i in range(n_material):
            self.materials[i].bumpMap = struct.unpack("i", buffer.read(4))[0]
        for i in range(n_material):
            self.materials[i].detailMap = struct.unpack("i", buffer.read(4))[0]

        if stream.dtsVersion == 25:
            for i in range(n_material):
                buffer.read(4)

        for i in range(n_material):
            self.materials[i].detailScale = struct.unpack("f", buffer.read(4))[0]
        for i in range(n_material):
            self.materials[i].reflectance = struct.unpack("f", buffer.read(4))[0]
