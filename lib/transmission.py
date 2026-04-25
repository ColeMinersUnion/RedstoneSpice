from base import Component, translateDirection, rotateOffset90, SignalType, SignalDict
from numpy import ndarray, array

#* yay! The annoying parts now

#Redstone Dust
class RedstoneDust(Component):
    def __init__(self, position: ndarray, facing: tuple):
        super().__init__(position)
        self.strength = 0
        #need to cache the signal strength from all input directions.
        self.inputs = SignalDict()
        self.state = False
        
        self.directions = [translateDirection(dir) for dir in facing]
        self.directions.append(array((0, -1, 0))) 
        #redstone always faces down and up


    def update(self, inputs: SignalDict)->SignalDict | None:
        
        """
        ignore power from inputs that we aren't facing
        """
        for block in inputs:
            if block in self.directions:
                self.inputs[block] = inputs[block]
                #updating self.inputs cache
        
        #TODO: Find a better way of encoding the redstone dust propogation.
        # I Think I did?
        self.strength = max([val for type_, val in self.inputs if type_ <= SignalType(3)])
        
        #redstone weakly powers blocks that it faces
        outputs = SignalDict()
        for dir in self.directions:
            outputs[dir] = (SignalType(3), self.strength-1)
        #WEAK -> is only from redstone dust. Dust needs to power more dust
        #still needs to be interpretted as weak for the mechanisms

    def __repr__(self):
        return f'Redstone Dust at {self.position} with signal strength {self.strength}'
    

class RedstoneRepeater(Component):
    def __init__(self, position: ndarray, facing: str, **kwargs):
        super().__init__(position)
        self.facing = facing
        self.output = False
        self.delay = 1
        self.locked = False
        self.count = 0

    def update(self, inputs: SignalDict)->SignalDict | None:
        #Redstone Repeaters and Comparators will output STRONG signals
        #This is for locking repeaters, and both happen to only have strong outputs
        output_dir = translateDirection(self.facing)
        input_dir = -1 * output_dir

        input_signal = inputs.get(input_dir)

        outputs = SignalDict()

        if(inputs[rotateOffset90(output_dir)+self.position][0] == SignalType(1)
           or inputs[rotateOffset90(input_dir) + self.position][0] == SignalType(1)):
            #lock the repeater
            self.locked = True
        elif self.locked:
            self.locked = False
        
        if self.locked:
            outputs[output_dir] = (SignalType(1), 15)
            return outputs
        
        self_ = array((0,0,0))

        #TODID: Fixed?
        """
        if Input SignalType, start count = 1
        Send update to self

        if inputs.get(self), increase count
            if count < self.delay, increase count, update self
            elif count < 2 * self.delay, increase count, update self & output_dir
            else (no updates, it should stay on)
        elif inputs.get(self) and not input_signal[0]
            turn off
        """
        if input_signal and input_signal[0]:
            self.count = 1
            outputs[self_] = (SignalType(0), 0)
            return outputs
        if self.count < self.delay:
            self.count += 1
            outputs[self_] = (SignalType(0), 0)
            return outputs
        elif self.count < 2 * self.delay:
            self.count += 1
            self.output = True
            outputs[self_] = (SignalType(0), 0)
            outputs[output_dir] = (SignalType(1), 15)
            return outputs
        elif input_signal and not input_signal[0]:
            self.count = 0 #reset
            if self.output:
                outputs[output_dir] = (SignalType(0), 15) #I no longer need to update itself
                self.output = False
            return outputs
        
        #No updates needed
        return

    def __repr__(self):
        return f'A{" locked " if self.locked else " "}Redstone Repeater with state {"on" if self.output else "off"}'
    

"""
Comparator
"""       
class Comparator(Component):
    def __init__(self, position: ndarray, facing: str, mode = "compare", **kwargs):
        super().__init__(position)
        self.facing = facing
        self.mode = True if mode == "subtract" else False
        self.count = 0

    def update(self, inputs: SignalDict)->SignalDict | None:
        output_dir = translateDirection(self.facing)
        main_input_dir = -1 * output_dir
        right = rotateOffset90(main_input_dir)
        left = rotateOffset90(output_dir)

        outputs = SignalDict()
        self_ = array((0,0,0))

        if self_ in inputs:
            outputs[output_dir] = (SignalType(1), inputs[self_][1])

        if(right not in inputs and left not in inputs and main_input_dir in inputs):
            #Maintain!
            outputs[self_] = (SignalType(1), inputs[main_input_dir][1])
            return outputs

        left_input = inputs[left][1]
        right_input = inputs[right][1]
        rear = inputs[main_input_dir][1]
        def _compare()->int:
            return rear if max(right_input, left_input) < rear else 0
            
        def _subtract()->int:
            return max(rear-max(right_input, left_input), 0)
        
        
        if self.mode and _subtract():
            outputs[self_] =(SignalType(1), _subtract())
        elif _compare():
            outputs[self_] =(SignalType(1), _compare())
        else:
            return
       