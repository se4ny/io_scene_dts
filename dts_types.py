"""  """
# vim: tabstop=8 noexpandtab

import dataclasses
import math
import mathutils
import struct
import typing

import bpy


def bit(n: int) -> int:
    return 1 << n


@dataclasses.dataclass
class Box(object):
    min: mathutils.Vector
    max: mathutils.Vector

    def __repr__(self):
        return "({}, {})".format(self.min, self.max)


class Node(object):
    
    __slots__ = ('name', 'parent', 'firstObject', 'firstChild', 'nextSibling', 'mat', 'bl_ob')
    def __init__(self, name: str, parent: int=-1) -> None:
        self.name: str = name
        self.parent: int = parent

        # Unused
        self.firstObject: int = -1
        self.firstChild: int = -1
        self.nextSibling: int = -1
        self.mat = mathutils.Matrix.Identity(4)

        # NOTE:TODO: Reference a Blender object. Might want to figure out a better way to do this.
        self.bl_ob: None | bpy.types.Object = None

    def write(self, stream):
        stream.write32(self.name, self.parent, self.firstObject, self.firstChild, self.nextSibling)

    @classmethod
    def read(cls, stream):
        obj = cls(stream.read32(), stream.read32())
        obj.firstObject = stream.read32()
        obj.firstChild = stream.read32()
        obj.nextSibling = stream.read32()
        return obj


class Object(object):

    def __init__(self, name: str, numMeshes: int, firstMesh: int, node: Node) -> None:
        self.name: str = name
        self.numMeshes: int = numMeshes
        self.firstMesh: int = firstMesh
        self.node: Node = node

        # Unused
        self.nextSibling: int = -1
        self.firstDecal: int = -1

    def write(self, stream):
        stream.write32(self.name, self.numMeshes, self.firstMesh, self.node, self.nextSibling, self.firstDecal)

    @classmethod
    def read(cls, stream) -> typing.Self:
        obj = cls(stream.read32(), stream.read32(), stream.read32(), stream.read32())
        obj.nextSibling = stream.read32()
        obj.firstDecal = stream.read32()
        return obj


class IflMaterial:

    def __init__(self, name, slot):
        self.name = name
        self.slot = slot

        # Unused
        self.firstFrame = -1
        self.time = -1
        self.numFrames = -1

    def write(self, stream):
        stream.write32(self.name, self.slot, self.firstFrame, self.time, self.numFrames)

    @classmethod
    def read(cls, stream):
        instance = cls(stream.read32(), stream.read32())
        instance.firstFrame = stream.read32()
        instance.time = stream.read32()
        instance.numFrames = stream.read32()
        return instance


class Decal(object):
    """  """

    def write(self, stream):
        pass

    @classmethod
    def read(cls, stream):
        pass


@dataclasses.dataclass
class Subshape(object):
    firstNode: int
    firstObject: int
    firstDecal: int
    numNodes: int
    numObjects: int
    numDecals: int


class ObjectState:

    def __init__(self, vis, frame, matFrame):
        self.vis = vis
        self.frame = frame
        self.matFrame = matFrame

    def write(self, stream):
        stream.write_float(self.vis)
        stream.write32(self.frame, self.matFrame)

    @classmethod
    def read(cls, stream):
        return cls(stream.read_float(), stream.read32(), stream.read32())


class Trigger:
    StateOn = bit(31)
    InvertOnReverse = bit(30)

    def __init__(self, state, pos):
        self.state = state
        self.pos = pos

    def write(self, stream):
        stream.write32(self.state)
        stream.write_float(self.pos)

    @classmethod
    def read(cls, stream):
        return cls(stream.read32(), stream.read_float())


class DetailLevel:

    def __init__(self,
                 name,
                 subshape,
                 objectDetail,
                 size,
                 avgError=-1.0,
                 maxError=-1.0,
                 polyCount=0):
        self.name = name
        self.subshape = subshape
        self.objectDetail = objectDetail
        self.size = size

        # Unused
        self.avgError = -1.0
        self.maxError = -1.0
        self.polyCount = 0

    def write(self, stream):
        stream.write32(self.name, self.subshape, self.objectDetail)
        stream.write_float(self.size, self.avgError, self.maxError)
        stream.write32(self.polyCount)

    @classmethod
    def read(cls, stream):
        obj = cls(stream.read32(), stream.read32(), stream.read32(),
                  stream.read_float())
        obj.avgError = stream.read_float()
        obj.maxError = stream.read_float()
        obj.polyCount = stream.read32()
        return obj


class Primitive:
    Triangles = 0x00000000
    Strip = 0x40000000
    Fan = 0x80000000
    TypeMask = 0xC0000000
    Indexed = 0x20000000
    NoMaterial = 0x10000000
    MaterialMask = 0x0FFFFFFF

    def __init__(self, firstElement, numElements, type):
        self.firstElement = firstElement
        self.numElements = numElements
        self.type = type

    def write(self, stream):
        stream.write16(self.firstElement, self.numElements)
        stream.write32(self.type)

    @classmethod
    def read(cls, stream):
        return cls(stream.read16(), stream.read16(), stream.read32())


class Mesh:
    StandardType = 0
    SkinType = 1
    DecalType = 2
    SortedType = 3
    NullType = 4
    TypeMask = 7

    TypeName = ["Standard", "Skin", "Decal", "Sorted", "Null"]

    Billboard = bit(31)
    HasDetailTexture = bit(30)
    BillboardZAxis = bit(29)
    UseEncodedNormals = bit(28)

    def __init__(self, mtype):
        self.bounds = Box(mathutils.Vector(), mathutils.Vector())
        self.center = mathutils.Vector()
        self.radius = 0
        self.numFrames = 1
        self.numMatFrames = 1
        self.vertsPerFrame = 1
        self.parent = -1
        self.type = mtype
        self.verts = []
        self.tverts = []
        self.normals = []
        self.enormals = []
        self.primitives = []
        self.indices = []
        self.mindices = []

        self.bones = []
        self.influences = []

    def get_type(self):
        return self.type & Mesh.TypeMask

    def get_flags(self, flag=0xFFFFFFFF):
        return self.type & flag

    def set_flags(self, flag):
        self.type |= flag

    def transformed_verts(self, mat):
        return map(lambda vert: mat * vert, self.verts)

    def calculate_bounds_mat(self, mat):
        box = Box(mathutils.Vector((10e30, 10e30, 10e30)),
                  mathutils.Vector((-10e30, -10e30, -10e30)))

        for vert in self.transformed_verts(mat):
            box.min.x = min(box.min.x, vert.x)
            box.min.y = min(box.min.y, vert.y)
            box.min.z = min(box.min.z, vert.z)
            box.max.x = max(box.max.x, vert.x)
            box.max.y = max(box.max.y, vert.y)
            box.max.z = max(box.max.z, vert.z)

        return box

    def calculate_radius_mat(self, mat, center):
        radius = 0.0

        for vert in self.transformed_verts(mat):
            radius = max(radius, (vert - center).length)

        return radius

    def calculate_radius_tube_mat(self, mat, center):
        radius = 0

        for vert in self.transformed_verts(mat):
            delta = vert - center
            radius = max(radius, mathutils.Vector((delta.x, delta.y)).length)

        return radius

    def write(self, stream):
        mtype = self.get_type()
        stream.write32(self.type)

        if mtype == Mesh.NullType:
            return

        stream.guard()
        stream.write32(self.numFrames, self.numMatFrames, self.parent)
        stream.write_box(self.bounds)
        stream.write_vec3(self.center)
        stream.write_float(self.radius)

        # Geometry data
        stream.write32(len(self.verts))
        for vert in self.verts:
            stream.write_vec3(vert)
        stream.write32(len(self.tverts))
        for tvert in self.tverts:
            stream.write_vec2(tvert)

        assert len(self.normals) == len(self.verts)
        assert len(self.enormals) == len(self.verts)
        for normal in self.normals:
            stream.write_vec3(normal)
        for enormal in self.enormals:
            stream.write8(enormal)

        # Primitives and other stuff
        stream.write32(len(self.primitives))
        for prim in self.primitives:
            prim.write(stream)

        #if stream.dtsVersion >= 25:
        stream.write32(len(self.indices))
        stream.write16(*self.indices)
        stream.write32(len(self.mindices))
        stream.write16(*self.mindices)
        stream.write32(self.vertsPerFrame)
        stream.write32(self.get_flags())
        stream.guard()

        if mtype == Mesh.SkinType:
            stream.write32(len(self.verts))
            for v in self.verts:
                stream.write_vec3(v)
            for v in self.normals:
                stream.write_vec3(v)
            stream.write8(*self.enormals)

            stream.write32(len(self.bones))
            for _, initial_transform in self.bones:
                for f in initial_transform:
                    stream.write_float(f)

            stream.write32(len(self.influences))
            for vertex_index, _, _ in self.influences:
                stream.write32(vertex_index)
            for _, bone_index, _ in self.influences:
                stream.write32(bone_index)
            for _, _, weight in self.influences:
                stream.write_float(weight)

            stream.write32(len(self.bones))
            for node_index, _ in self.bones:
                stream.write32(node_index)

            stream.guard()
        elif mtype != Mesh.StandardType:
            raise ValueError("cannot write {} mesh".format(mtype))

    def read_standard_mesh(self, stream):
        stream.guard()

        self.numFrames = stream.read32()
        self.numMatFrames = stream.read32()
        self.parent = stream.read32()
        self.bounds = stream.read_box()
        self.center = stream.read_vec3()
        self.radius = stream.read_float()

        # Geometry data
        n_vert = stream.read32()
        self.verts = [stream.read_vec3() for i in range(n_vert)]
        n_tvert = stream.read32()
        self.tverts = [stream.read_vec2() for i in range(n_tvert)]
        self.normals = [stream.read_vec3() for i in range(n_vert)]
        # TODO: don't read this when not relevant
        self.enormals = [stream.read8() for i in range(n_vert)]

        # Primitives and other stuff
        self.primitives = [
            Primitive.read(stream) for i in range(stream.read32())
        ]
        self.indices = [stream.read16() for i in range(stream.read32())]
        self.mindices = [stream.read16() for i in range(stream.read32())]
        self.vertsPerFrame = stream.read32()
        self.set_flags(stream.read32())

        stream.guard()

    def read_skin_mesh(self, stream):
        self.read_standard_mesh(stream)

        sz = stream.read32()
        _ = [stream.read_vec3() for i in range(sz)]
        _ = [stream.read_vec3() for i in range(sz)]
        _ = [stream.read8() for i in range(sz)]

        sz = stream.read32()
        self.bones = [[None, None] for i in range(sz)]

        for i in range(sz):
            initial_transform = [stream.read_float() for i in range(16)]
            self.bones[i][1] = initial_transform

        sz = stream.read32()
        self.influences = [[None, None, None] for i in range(sz)]

        for i in range(sz):
            self.influences[i][0] = stream.read32()
        for i in range(sz):
            self.influences[i][1] = stream.read32()
        for i in range(sz):
            self.influences[i][2] = stream.read_float()

        sz = stream.read32()
        assert sz == len(self.bones)

        for i in range(sz):
            self.bones[i][0] = stream.read32()

        stream.guard()

    @classmethod
    def read(cls, stream):
        mtype = stream.read32() & Mesh.TypeMask
        mesh = cls(mtype)

        if mtype == Mesh.StandardType:
            mesh.read_standard_mesh(stream)
        elif mtype == Mesh.SkinType:
            mesh.read_skin_mesh(stream)
        # others here
        elif mtype == Mesh.NullType:
            pass
        else:
            raise ValueError("don't know how to read {} mesh".format(mtype))

        return mesh


class Material:
    SWrap = 0x00000001
    TWrap = 0x00000002
    Translucent = 0x00000004
    Additive = 0x00000008
    Subtractive = 0x00000010
    SelfIlluminating = 0x00000020
    NeverEnvMap = 0x00000040
    NoMipMap = 0x00000080
    MipMapZeroBorder = 0x00000100
    IFLMaterial = 0x08000000
    IFLFrame = 0x10000000
    DetailMap = 0x20000000
    BumpMap = 0x40000000
    ReflectanceMap = 0x80000000
    AuxiliaryMask = 0xE0000000

    def __init__(self,
                 name="",
                 flags=0,
                 reflectanceMap=-1,
                 bumpMap=-1,
                 detailMap=-1,
                 detailScale=1.0,
                 reflectance=0.0):
        self.name = name
        self.flags = flags
        self.reflectanceMap = reflectanceMap
        self.bumpMap = bumpMap
        self.detailMap = detailMap
        self.detailScale = detailScale
        self.reflectance = reflectance


def read_bit_set(fd):
    dummy, numWords = struct.unpack("<ii", fd.read(8))
    words = struct.unpack(str(numWords) + "i", fd.read(4 * numWords))
    total = len(words) * 32
    return [(words[i >> 5] & (1 << (i & 31))) != 0 for i in range(total)]


def write_bit_set(fd, bits):
    numWords = int(math.ceil(len(bits) / 32.0))
    words = [0] * numWords

    for i, bit in enumerate(bits):
        if bit:
            words[i >> 5] |= 1 << (i & 31)

    fd.write(struct.pack("<ii", numWords, numWords))

    for word in words:
        fd.write(struct.pack("<i", word))


class Sequence:
    UniformScale = bit(0)
    AlignedScale = bit(1)
    ArbitraryScale = bit(2)
    Blend = bit(3)
    Cyclic = bit(4)
    MakePath = bit(5)
    IflInit = bit(6)
    HasTranslucency = bit(7)

    def __init__(self):
        # todo: get rid of this
        self.nameIndex = -1
        self.name = None
        self.flags = 0
        self.numKeyframes = 0
        self.duration = 0
        self.priority = 0
        self.firstGroundFrame = 0
        self.numGroundFrames = 0
        self.baseRotation = 0
        self.baseTranslation = 0
        self.baseScale = 0
        self.baseObjectState = 0
        self.baseDecalState = 0
        self.firstTrigger = 0
        self.numTriggers = 0
        self.toolBegin = 0

        self.rotationMatters = []
        self.translationMatters = []
        self.scaleMatters = []
        self.decalMatters = []
        self.iflMatters = []
        self.visMatters = []
        self.frameMatters = []
        self.matFrameMatters = []

    def write(self, fd, writeIndex=True):
        if writeIndex:
            fd.write(struct.pack("<i", self.nameIndex))
        fd.write(struct.pack("<I", self.flags))
        fd.write(struct.pack("<i", self.numKeyframes))
        fd.write(struct.pack("<f", self.duration))
        fd.write(struct.pack("<i", self.priority))
        fd.write(struct.pack("<i", self.firstGroundFrame))
        fd.write(struct.pack("<i", self.numGroundFrames))
        fd.write(struct.pack("<i", self.baseRotation))
        fd.write(struct.pack("<i", self.baseTranslation))
        fd.write(struct.pack("<i", self.baseScale))
        fd.write(struct.pack("<i", self.baseObjectState))
        fd.write(struct.pack("<i", self.baseDecalState))
        fd.write(struct.pack("<i", self.firstTrigger))
        fd.write(struct.pack("<i", self.numTriggers))
        fd.write(struct.pack("<f", self.toolBegin))

        write_bit_set(fd, self.rotationMatters)
        write_bit_set(fd, self.translationMatters)
        write_bit_set(fd, self.scaleMatters)
        write_bit_set(fd, self.decalMatters)
        write_bit_set(fd, self.iflMatters)
        write_bit_set(fd, self.visMatters)
        write_bit_set(fd, self.frameMatters)
        write_bit_set(fd, self.matFrameMatters)

    @classmethod
    def read_bit_set(cls, fd):
        dummy = struct.unpack("i", fd.read(4))[0]
        numWords = struct.unpack("i", fd.read(4))[0]
        return struct.unpack(str(numWords) + "i", fd.read(4 * numWords))

    @classmethod
    def read(cls, fd, readIndex=True):
        seq = cls()

        if readIndex:
            seq.nameIndex = struct.unpack("i", fd.read(4))[0]
        seq.flags = struct.unpack("I", fd.read(4))[0]
        seq.numKeyframes = struct.unpack("i", fd.read(4))[0]
        seq.duration = struct.unpack("f", fd.read(4))[0]
        seq.priority = struct.unpack("i", fd.read(4))[0]
        seq.firstGroundFrame = struct.unpack("i", fd.read(4))[0]
        seq.numGroundFrames = struct.unpack("i", fd.read(4))[0]
        seq.baseRotation = struct.unpack("i", fd.read(4))[0]
        seq.baseTranslation = struct.unpack("i", fd.read(4))[0]
        seq.baseScale = struct.unpack("i", fd.read(4))[0]
        seq.baseObjectState = struct.unpack("i", fd.read(4))[0]
        seq.baseDecalState = struct.unpack("i", fd.read(4))[0]
        seq.firstTrigger = struct.unpack("i", fd.read(4))[0]
        seq.numTriggers = struct.unpack("i", fd.read(4))[0]
        seq.toolBegin = struct.unpack("f", fd.read(4))[0]

        seq.rotationMatters = read_bit_set(fd)
        seq.translationMatters = read_bit_set(fd)
        seq.scaleMatters = read_bit_set(fd)
        seq.decalMatters = read_bit_set(fd)
        seq.iflMatters = read_bit_set(fd)
        seq.visMatters = read_bit_set(fd)
        seq.frameMatters = read_bit_set(fd)
        seq.matFrameMatters = read_bit_set(fd)

        return seq
