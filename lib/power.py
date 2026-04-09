from base import Component, translateDirection
from numpy import ndarray, array
from collections import deque

#TODO: Better type hints (on iterables)

"""
For submission:
Lever, Button, RTorch, RBlock?
"""
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
        super().__init__(position)
        self.facing = facing
        self.state = kwargs.get("lit", True)
        #There shouldn't be any other block_state attributes

        #This is the block that the torch is placed on. 
        self.block = -1 * translateDirection(self.facing)
        self.history = self._cached_history(self.state, 30)

        """
        The facing direction is the direction it is facing
        Since this state is only tracked on walls, 
        if there is no state, the torch is on the ground 
        """

    """
    The torch burns out if there are 8 state changes in 30 redstone ticks
    It doesn't turn back on until there are less than 8 state changes in 30 ticks
    """
    class _cached_history:
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
    def update(self, inputs: dict)->dict | None:
        prev_state = self.state
        if self.history.burnout():
            self.state = False
        elif self.block in inputs:
            #TODO: Figure out how inputs are sent
            if inputs[self.block]:
                self.state = False
            else:
                self.state = True

        #update history
        #burnout. 
        self.history.append(self.state)

        
        #If the updates changed the torch
        if(prev_state != self.state):
            outputs = {}
            for d in directions:
                if d == translateDirection(self.facing):
                    outputs[d + self.position] = ("strong", 15)
                elif d != self.block:
                    outputs[d + self.position] = ("weak", 15)
            return outputs
        return
    

class Button(source):
    def __init__(self, position: ndarray, facing: str, material: str = "stone", **kwargs):
        super().__init__(position)
        self.facing = facing
        self.block = -1 * translateDirection(self.facing)

        """
        Stone buttons hold for 20 game ticks
        Wood buttons hold for 30 game ticks. 
        2 game ticks = 1 redstone tick (with a rising and falling edge)
        """
        self.sustain = 10 if material == "stone" else 15
        self.state = False
        self.duration = 0

    def press(self) -> None:
        self.state = True
        self.duration = self.sustain

    def update(self) -> dict | None:
        #Strongly powers the block it's on, weakly powers adjacent spots. 
        if not self.state:
            return
        if self.state and not self.duration:
            self.state = False
        
        self.duration = max(0, self.duration-1)
        outputs = {}
        for d in directions:
            if d == self.block:
                outputs[d + self.position] = ("strong", 15)
            else:
                outputs[d + self.position] = ("weak", 15)
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

    def update(self)->dict | None:
        #Strongly powers the block it's on, weakly powers adjacent spots. 
        if self.state == self.prev_state:
            return
        outputs = {}
        for d in directions:
            if d == self.block:
                outputs[d + self.position] = ("strong", 15)
            else:
                outputs[d + self.position] = ("weak", 15)
        self.prev_state = self.state
        return outputs

class RedstoneBlock(source):
    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)

    def update(self, initial_tick: bool = False) -> dict | None:
        if not initial_tick:
            return
        outputs = {}
        for d in directions:
            outputs[d + self.position] = ("weak", 15)        
