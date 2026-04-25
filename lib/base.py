from numpy import ndarray, array
from enum import Enum
from typing import Iterator

#This makes my life a bit easier
class SignalType(Enum):
    no_power=0
    STRONG=1
    strong=2
    WEAK=3
    weak=4
    indirect=5

#Overengineered solution to numpy arrays not being hashable
#I wanted to do matrix math and use basic dictionary functions
class SignalDict:
    #need to assign each ndarray to a str for hashing
    DIRECTION_HASHES = {
            "self":     array([0,  0,  0]),
            "east":     array([1,  0,  0]),
            "west":     array([-1, 0,  0]),
            "up":       array([0,  1,  0]),
            "down":     array([0, -1,  0]),
            "south":    array([0,  0,  1]),
            "north":    array([0,  0, -1]),
        }

    _Lookup_Table: dict[tuple, str] = {
        tuple(v): k for k, v in DIRECTION_HASHES.items()
    }


    def __init__(self):
        self._data: dict[tuple, tuple[SignalType, int]] = {}

    """
    Helper function
    This function converts the numpy array to a hashable str
    not visible to the user, only for internal use only
    """
    @staticmethod
    def _to_tuple(key: ndarray) -> tuple:
        if not isinstance(key, ndarray):
            raise TypeError(f"Keys must be numpy arrays, got {type(key).__name__}")
        t = tuple(int(x) for x in key)
        if t not in SignalDict._Lookup_Table:
            raise KeyError(
                f"Invalid direction {key}. Must be one of the six cardinal "
                f"offsets or the origin (0,0,0)."
            )
        return t
    

    """
    Another helper function
    Used to validate the value of the dict
    """
    @staticmethod
    def _validate_value(value: tuple) -> None:
        if (
            not isinstance(value, tuple)
            or len(value) != 2
            or not isinstance(value[0], SignalType)
            or not isinstance(value[1], int)
            or not (0 <= value[1] <= 15)
        ):
            raise ValueError(
                f"Values must be (SignalType, int 0-15), got {value!r}"
            )
    
    #All the basic dictionary functions
    def __setitem__(self, key: ndarray, value: tuple[SignalType, int]) -> None:
        SignalDict._validate_value(value)
        self._data[self._to_tuple(key)] = value
 
    def __getitem__(self, key: ndarray) -> tuple[SignalType, int]:
        t = self._to_tuple(key)
        if t not in self._data:
            raise KeyError(f"Direction {key} not set.")
        return self._data[t]
 
    def __delitem__(self, key: ndarray) -> None:
        t = self._to_tuple(key)
        if t not in self._data:
            raise KeyError(f"Direction {key} not set.")
        del self._data[t]
 
    def __contains__(self, key: object) -> bool:
        if not isinstance(key, ndarray):
            return False
        try:
            return SignalDict._to_tuple(key) in self._data
        except KeyError:
            return False
 
    def __len__(self) -> int:
        return len(self._data)
 
    def __repr__(self) -> str:
        items = ", ".join(
            f"{SignalDict._Lookup_Table[t]}: {v}" for t, v in self._data.items()
        )
        return f"SignalDict({{{items}}})"

    """
    Dictionary functions!
    Idt I use any of these yet, 
    but I know I'm going to expect it to be there so I'm adding it in now
    """
    def keys(self) -> list[ndarray]:
        return [array(t) for t in self._data]
 
    def values(self) -> list[tuple[SignalType, int]]:
        return list(self._data.values())
 
    def items(self) -> list[tuple[ndarray, tuple[SignalType, int]]]:
        return [(array(t), v) for t, v in self._data.items()]

    def get(self, key: ndarray, default: tuple[SignalType, int] | None = None) -> tuple[SignalType, int] | None:
        try:
            return self[key]
        except KeyError:
            return default
 
    def pop(self, key: ndarray, *args) -> tuple[SignalType, int]:
        t = self._to_tuple(key)
        if args:
            return self._data.pop(t, args[0])
        if t not in self._data:
            raise KeyError(f"Direction {key} not set.")
        return self._data.pop(t)
 
    def clear(self) -> None:
        """Remove all entries."""
        self._data.clear()


    """
    These functions can take a lambda argument to define how they search
    I disabled the ruff and pylance warnings about declaring a lambda
    """
    def any(self, predicate=None) -> bool:
        if predicate is None:
            predicate = lambda s, n: n > 0  # noqa: E731
        return any(predicate(sig, strength) for sig, strength in self._data.values())

    def all(self, predicate=None) -> bool:
        if not self._data:
            return True  
        if predicate is None:
            predicate = lambda s, n: n > 0  # noqa: E731
        return all(predicate(sig, strength) for sig, strength in self._data.values())



    #Making the class iterable
    def __iter__(self) -> Iterator[ndarray]:
        """Iterate over direction arrays (like dict iterates over keys)."""
        return iter(self.keys())


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
        """
        conductive blocks can be
        strong powered, (can power redstone dust)
        weakly powered, (only indirect power)
        indirect power, (does not spread, activates mechanism)
        """

    # To be called each tick
    # weak -> indirect, strong->weak
    def update(self, input: SignalDict):

        #find strongest (type) of 

        pass

    def __repr__(self):
        return f"{self.__class__.__name__}(powered={self.powered}) at {self.position}"

class TransparentBlock(Component):
    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)
        self.transparent = True
        self.block_state = kwargs

    #Cannot be powered, need to do vertical redstone in builder
    def update(self, input: SignalDict)->None:
        return

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
        
def rotateOffset90(direction: ndarray)->ndarray:
    match direction.tolist():
        case [1, 0, 0]:
            return array((0, 0, 1))
        case [-1, 0, 0]:
            return array((0, 0, -1))
        case [0, 0, 1]:
            return array((-1, 0, 0))
        case [0, 0, -1]:
            return array((1, 0, 0))
    raise ValueError("Improper Direction")
        