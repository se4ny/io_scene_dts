"""  """

import ctypes
import mathutils
import struct

import dts_utils

# Shortcut for reading & writing struct data from & to a file descriptor
def ws(fd, spec, *values):
    fd.write(struct.pack(spec, *values))


def read_multi(fd, count, spec):
    spec = str(count) + spec
    return struct.unpack(spec, fd.read(struct.calcsize(spec)))


class OutStream(object):

    def __init__(self, dtsVersion=24, exporterVersion=0):
        self.dtsVersion = dtsVersion
        self.exporterVersion = exporterVersion
        self.sequence32 = ctypes.c_int(0)
        self.sequence16 = ctypes.c_short(0)
        self.sequence8 = ctypes.c_byte(0)
        self.buffer32 = []
        self.buffer16 = []
        self.buffer8 = []

    def guard(self, specific=None):
        if specific != None:
            assert ctypes.c_int(specific).value == self.sequence32.value
        self.write32(self.sequence32.value)
        self.write16(self.sequence16.value)
        self.write8(self.sequence8.value)
        self.sequence32.value += 1
        self.sequence16.value += 1
        self.sequence8.value += 1

    def flush(self, fd):
        # Force all buffers to have a size multiple of 4 bytes
        if len(self.buffer16) % 2 == 1: self.buffer16.append(0)
        while len(self.buffer8) % 4 != 0:
            self.buffer8.append(0)

        end32 = len(self.buffer32)
        end16 = end32 + len(self.buffer16) // 2
        end8 = end16 + len(self.buffer8) // 4

        fd.write(
            struct.pack("hhiii", self.dtsVersion, self.exporterVersion, end8, end32,
                 end16))
        fd.write(struct.pack(str(len(self.buffer32)) + "i", *self.buffer32))
        fd.write(struct.pack(str(len(self.buffer16)) + "h", *self.buffer16))
        fd.write(struct.pack(str(len(self.buffer8)) + "b", *self.buffer8))

    def write32(self, *values):
        for value in values:
            assert -2147483648 <= value <= 2147483647, "value {} out of range".format(
                value)
            assert type(value) == int, "type is {}, must be {}".format(
                type(value), int)
        self.buffer32.extend(values)

    def write16(self, *values):
        #for value in values:
        #	assert -32768 <= value <= 32767, "value {} out of range".format(value)
        #	assert type(value) == int, "type is {}, must be {}".format(type(value), int)
        #self.buffer16.extend(values)
        self.buffer16.extend(map(lambda v: ctypes.c_short(int(v)).value, values))

    def write8(self, *values):
        for value in values:
            assert -128 <= value <= 127, "value {} out of range".format(value)
            assert type(value) == int, "type is {}, must be {}".format(
                type(value), int)
        self.buffer8.extend(values)

    def write_u8(self, num):
        assert 0 <= num <= 255, num
        self.write8(struct.unpack("b", struct.pack("B", num))[0])

    def write_float(self, *values):
        self.write32(*map(lambda f: struct.unpack("i", struct.pack("f", f))[0], values))

    def write_string(self, string):
        self.write8(*string.encode("cp1252"))
        self.write8(0)

    def write_vec3(self, v):
        self.write_float(v.x, v.y, v.z)

    def write_vec2(self, v):
        self.write_float(v.x, v.y)

    def write_box(self, box):
        self.write_vec3(box.min)
        self.write_vec3(box.max)

    def write_quat(self, quat):
        self.write16(
            ctypes.c_short(int(quat.x * 32767)).value,
            ctypes.c_short(int(quat.y * 32767)).value,
            ctypes.c_short(int(quat.z * 32767)).value,
            ctypes.c_short(int(quat.w * -32767)).value)


class InStream(object):
    """  """
    __slots__ = ('sequence32', 'sequence16', 'sequence8', 'dtsVersion', 'exporterVersion', 'buffer32', 'buffer16', 'buffer8')
    def __init__(self, fd):
        self.sequence32 = ctypes.c_int(0)
        self.sequence16 = ctypes.c_short(0)
        self.sequence8 = ctypes.c_byte(0)
        self.dtsVersion, self.exporterVersion = struct.unpack("hh", fd.read(4))
        end8, end32, end16 = struct.unpack("iii", fd.read(12))
        num32 = end32
        num16 = (end16 - end32) * 2
        num8 = (end8 - end16) * 4
        self.buffer32 = bytearray("i", read_multi(fd, num32, "i"))
        self.buffer16 = bytearray("h", read_multi(fd, num16, "h"))
        self.buffer8 = bytearray("b", read_multi(fd, num8, "b"))
        self.tell32 = 0
        self.tell16 = 0
        self.tell8 = 0

    def guard(self, specific: None | int=None) -> None:
        """  
        
        :param specific:
        :raises :py:`EOFError`:
        :raises :py:`AssertionError`:
        """
        assert specific is None or ctypes.c_int(specific).value == self.sequence32.value
        assert self.sequence32.value == self.read32()
        assert self.sequence16.value == self.read16()
        assert self.sequence8.value == self.read8()
        self.sequence32.value += 1
        self.sequence16.value += 1
        self.sequence8.value += 1

    def read32(self) -> int:
        """  
        
        :raises :py:`EOFError`:
        """
        if self.tell32 >= len(self.buffer32):
            raise EOFError()

        data = self.buffer32[self.tell32]
        self.tell32 += 1
        return data

    def read16(self):
        """  
        
        :raises :py:`EOFError`:
        """
        if self.tell16 >= len(self.buffer16):
            raise EOFError()

        data = self.buffer16[self.tell16]
        self.tell16 += 1
        return data

    def read8(self):
        """  
        
        :raises :py:`EOFError`:
        """
        if self.tell8 >= len(self.buffer8):
            raise EOFError()

        data = self.buffer8[self.tell8]
        self.tell8 += 1
        return data

    def read_float(self):
        """  
        
        :raises :py:`EOFError`:
        """
        return struct.unpack("f", struct.pack("i", self.read32()))[0]

    def read_string(self):
        """  
        
        :raises :py:`EOFError`:
        """
        buf = bytearray()
        while True:
            byte = self.read8()
            if byte == 0:
                break
            else:
                buf.append(byte)
        return buf.decode("cp1252")

    def read_vec3(self):
        """  
        
        :raises :py:`EOFError`:
        """
        return mathutils.Vector((self.read_float(), self.read_float(), self.read_float()))

    def read_vec2(self):
        """  
        
        :raises :py:`EOFError`:
        """
        return mathutils.Vector((self.read_float(), self.read_float()))

    def read_box(self):
        """  
        
        :raises :py:`EOFError`:
        """
        return dts_utils.Box(self.read_vec3(), self.read_vec3())

    def read_quat(self):
        """  
        
        :raises :py:`EOFError`:
        """
        x = self.read16() / 32767
        y = self.read16() / 32767
        z = self.read16() / 32767
        w = self.read16() / -32767
        return mathutils.Quaternion((w, x, y, z))
