"""  """
import dataclasses
import mathutils


@dataclasses.dataclass
class Box(object):
    """  """
    minimum: mathutils.Vector
    maximum: mathutils.Vector

    def __repr__(self):
        return "({}, {})".format(self.minimum, self.maximum)
