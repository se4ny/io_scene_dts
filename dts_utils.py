"""  """
import dataclasses
import mathutils


@dataclasses.dataclass
class Box(object):
    """  """
    min: mathutils.Vector
    max: mathutils.Vector

    def __repr__(self):
        return "({}, {})".format(self.min, self.max)
