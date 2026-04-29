from lib.base import Component, translateDirection, SignalType, SignalDict
from numpy import ndarray, array
from collections import deque


class source(Component):
    def __init__(self, position: ndarray):
        super().__init__(position)
        self.state = False

#named arguments are immutable, kwargs may change during simulation
directions  =  [array((1, 0, 0)), array((-1, 0, 0)),
                array((0, 1, 0)), array((0, -1, 0)),
                array((0, 0, 1)), array((0, 0, -1))]


#I'm wrapping redstone torch and redstone wall torch together
class RedstoneTorch(source):
    def __init__(self, position: ndarray, facing: str = "up", **kwargs):
        """
        The facing direction is the direction it is facing
        Since this state is only tracked on walls, 
        if there is no state, the torch is on the ground 
        """
        super().__init__(position)
        self.facing = facing
        self.state = kwargs.get("lit", True)
        #There shouldn't be any other block_state attributes

        #This is the block that the torch is placed on. 
        self.block = -1 * translateDirection(self.facing)
        self.history = self._cached_history(self.state, 30)

        

    
    class _cached_history:
        """
        The torch burns out if there are 8 state changes in 30 redstone ticks
        It doesn't turn back on until there are less than 8 state changes in 30 ticks
        """
        def __init__(self, initial_state: bool, length):
            self.length = length
            self.history = deque([initial_state] * self.length, maxlen=self.length)

        def append(self, state: bool)->None:
            self.history.pop()
            self.history.appendleft(state)

        def burnout(self)->bool:
            prev = self.history.pop()
            self.history.appendleft(prev)
            changes = 0
            for _ in range(self.length):
                curr = self.history.pop()
                self.history.appendleft(curr)
                if prev != curr:
                    changes += 1
                prev = curr
            return (changes > 7)
    

    """
    Should handle burnout
    """
    def update(self, inputs: SignalDict) -> SignalDict | None:
        prev_state = self.state

        if self.history.burnout():
            self.state = False
        elif self.block in inputs:
            self.state = inputs[self.block][1] == 0

        self.history.append(self.state)

        if prev_state != self.state:
            outputs = SignalDict()
            for d in directions:
                if (d == translateDirection(self.facing)).all():
                    outputs[d] = (SignalType.strong, 15)
                elif not (d == self.block).all():
                    outputs[d] = (SignalType.weak, 15)
            return outputs
        return None
    

class Button(source):
    def __init__(self, position: ndarray, facing: str, material: str = "stone", **kwargs):
        super().__init__(position)
        self.facing = facing
        self.block = -1 * translateDirection(self.facing)

        self.sustain = 10 if material == "stone" else 15
        self.state = False
        self.duration = 0

    def press(self) -> None:
        self.state = True
        self.duration = self.sustain

    def update(self, inputs: SignalDict | None = None) -> SignalDict | None:
        if not self.state:
            return None


        self.duration = max(0, self.duration - 1)
        if self.duration == 0:
            self.state = False
            # Emit a zero-strength update so downstream knows power dropped.
            off_outputs = SignalDict()
            for d in directions:
                off_outputs[d] = (SignalType.no_power, 0)
            return off_outputs

        outputs = SignalDict()
        for d in directions:
            if (d == self.block).all():
                outputs[d] = (SignalType.strong, 15)
            else:
                outputs[d] = (SignalType.weak, 15)
        return outputs

class Lever(source):
    def __init__(self, position: ndarray, facing: str, **kwargs):
        super().__init__(position)
        self.facing = facing
        self.block = -1 * translateDirection(self.facing)
        self.state = False
        self.prev_state = False

    def toggle(self) -> None:
        self.state = not self.state

    def update(self, inputs: SignalDict | None = None) -> SignalDict | None:
        if self.state == self.prev_state:
            return None
        self.prev_state = self.state
        outputs = SignalDict()
        for d in directions:
            if (d == self.block).all():
                outputs[d] = (SignalType.strong, 15) if self.state else (SignalType.no_power, 0)
            else:
                outputs[d] = (SignalType.weak, 15) if self.state else (SignalType.no_power, 0)
        return outputs

class RedstoneBlock(source):
    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)
        self.state = True   # always on

    def update(self, inputs: SignalDict | None = None) -> SignalDict | None:
        outputs = SignalDict()
        for d in directions:
            outputs[d] = (SignalType.weak, 15)
        return outputs