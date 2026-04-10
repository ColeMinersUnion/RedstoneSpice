from base import Component, translateDirection, rotateOffset90
from numpy import ndarray, array

#* yay! The annoying parts now

#Redstone Dust
class RedstoneDust(Component):
    def __init__(self, position: ndarray, facing: tuple):
        super().__init__(position)
        self.strength = 0
        #need to cache the signal strength from all input directions.
        self.inputs = {} 
        self.state = False
        
        self.directions = [translateDirection(dir) for dir in facing]
        self.directions.append(array((0, -1, 0))) 
        #redstone always faces down and up

    def update(self, inputs: dict):
        
        """
        ignore power from inputs that we aren't facing
        """
        for block in inputs:
            if block == self.position + array((0, 1, 0)):
                continue
            if block in self.directions:
                self.inputs[block] = inputs[block]
                #updating self.inputs cache
        
        #TODO: Find a better way of encoding the redstone dust propogation.
        self.strength = max([val for type_, val in self.inputs if type_ == "strong" or type_ == "WEAK"])
        
        #redstone weakly powers blocks that it faces
        outputs = {}
        for dir in self.directions:
            outputs[self.position + dir] = ("WEAK", self.strength-1)
        #WEAK -> is only from redstone dust. Dust needs to power more dust
        #still needs to be interpretted as weak for the mechanisms

    def __repr__(self):
        print(f'Redstone Dust at {self.position} with signal strength {self.strength}')
    

class RedstoneRepeater(Component):
    def __init__(self, position: ndarray, facing: str, **kwargs):
        super().__init__(position)
        self.facing = facing
        self.output = False
        self.delay = 1
        self.locked = False

    def update(self, inputs: dict)->dict | None:
        #Redstone Repeaters and Comparators will output STRONG signals
        #This is for locking repeaters, and both happen to only have strong outputs
        input_dir = -1 * translateDirection(self.facing)
        input_signal = inputs.get(self.position + input_dir, 0)

        if(inputs[rotateOffset90(translateDirection(self.facing))+self.position][0] == "STRONG"
           or inputs[rotateOffset90(input_dir) + self.position][0] == "STRONG"):
            #lock the repeater
            pass

        #TODO: Send things to scheduler
        #TODO: Locking
        #TODO: Signal Extension (pulse)

        pass