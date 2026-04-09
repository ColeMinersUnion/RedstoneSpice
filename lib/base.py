from numpy import ndarray, array

#* Creating all of the abstract classes I'll use
"""
This is the base class for most components I'll go on to define.
This will define the main parameters, and key functions
"""
class Component:
    def __init__(self, position: ndarray):
        #Arguments
        self.position = position

        self.movable = False
        self.mutable = True
        self.transparent = False

    def __repr__(self):
        return f"{self.__class__.__name__} at {self.position}"
    

"""
Constants.
- There are a few constants that I want to include
- Signal Strength Constant
- Used for always high signals, and for specific signal strengths like those pulled from a lectern

This class will have very little behavior, and is purely for simulation shortcuts.
"""
class Constant(Component):
    def __init__(self, position: ndarray, signal_strength: int):
        super().__init__(position)
        self.signal_strength = signal_strength
        self.mutable = False

    def __repr__(self):
        return f"Constant({self.signal_strength}) at {self.position}"


"""
Most blocks will fall into these two categories
"""
class Block(Component):
    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)
        self.powered = kwargs.get("powered", False)
        self.block_state = kwargs

    # To be called each tick
    def update(self, input: dict):
        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(powered={self.powered}) at {self.position}"

class TransparentBlock(Component):
    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)
        self.transparent = True
        self.block_state = kwargs

    def update(self, input: dict):
        pass

    def __repr__(self):
        return f"{self.__class__.__name__} at {self.position}"
    
"""
Update, Each block will look at all inputs at each tick
Then, it will create a new output, and send it to the circuit class
The circuit class will be responsible for sending that output to all connected components
"""


"""
Translating block states into usable coordinate offsets
Source: https://minecraft.wiki/w/Coordinates#Coordinate_system
"""
def translateDirection(direction: str):
    match direction:
        case "east":
            return array((1, 0, 0))
        case "west":
            return array((-1, 0, 0))
        case "north":
            return array((0, 0, -1))
        case "south":
            return array((0, 0, 1))
        case "up":
            return array((0, 1, 0))
        case "down":
            return array((0, -1, 0))
    raise ValueError("Invalid Direction")
        