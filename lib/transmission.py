from lib.base import Component, translateDirection, rotateOffset90, SignalType, SignalDict
from numpy import ndarray, array

#* yay! The annoying parts now

# ---------------------------------------------------------------------------
# Helper: compare two numpy direction arrays for equality.
# Plain `==` returns an element-wise array, which breaks `in` / `if` tests.
# ---------------------------------------------------------------------------
def _dir_eq(a: ndarray, b: ndarray) -> bool:
    return bool((a == b).all())

def _dir_in(needle: ndarray, haystack: list[ndarray]) -> bool:
    return any(_dir_eq(needle, h) for h in haystack)


# ---------------------------------------------------------------------------
# Redstone Dust
# ---------------------------------------------------------------------------
class RedstoneDust(Component):
    def __init__(self, position: ndarray, facing: tuple):
        super().__init__(position)
        self.strength = 0
        # Cache the signal strength from all valid input directions.
        self.inputs = SignalDict()
        self.state = False
        
        self.directions = [translateDirection(dir) for dir in facing]
        self.directions.append(array((0, -1, 0)))
        # Redstone dust always connects downward (and upward via slope,
        # but down is the minimum we always include).

    def update(self, inputs: SignalDict) -> SignalDict | None:
        """
        Accept signals only from directions the dust is facing.
        Propagate a WEAK signal at (received_strength - 1) onward.
        Only emits an output when strength actually changes, so unpowered
        dust doesn't flood the circuit with zero-strength noise.
        """
        # Update the cached inputs for directions we are facing.
        for block in inputs:
            if _dir_in(block, self.directions):
                self.inputs[block] = inputs[block]

        # Compute new strength from cached inputs.
        # Accept any signal type except no_power — the WEAK(3)/weak(4) distinction
        # matters for dust-to-dust vs source-to-dust propagation semantics, but
        # both carry a real strength that should contribute to this dust's level.
        strengths = [val for _type, val in self.inputs.values()
                     if _type != SignalType.no_power]
        new_strength = max(strengths) if strengths else 0

        # No change — nothing to propagate.
        if new_strength == self.strength:
            return None

        self.strength = new_strength
        self.state = self.strength > 0

        out_strength = max(0, self.strength - 1)

        outputs = SignalDict()
        for d in self.directions:
            outputs[d] = (SignalType.WEAK, out_strength)
        return outputs

    def __repr__(self):
        return f'Redstone Dust at {self.position} with signal strength {self.strength}'
    

# ---------------------------------------------------------------------------
# Repeater
# ---------------------------------------------------------------------------
class Repeater(Component):
    def __init__(self, position: ndarray, facing: str, delay: int = 1, **kwargs):
        super().__init__(position)
        self.facing = facing
        self.output = False
        self.delay = max(1, delay)
        self.locked = False
        self.count = 0

    def update(self, inputs: SignalDict) -> SignalDict | None:
        output_dir = translateDirection(self.facing)
        input_dir = -1 * output_dir

        input_signal = inputs.get(input_dir)

        outputs = SignalDict()

        # BUG 5 FIX: use relative offsets only — do NOT add self.position.
        # rotateOffset90 gives the 90° lateral direction; that offset is
        # exactly the key the Circuit puts in our inputs SignalDict.
        left_dir  = rotateOffset90(output_dir)
        right_dir = rotateOffset90(input_dir)

        left_signal  = inputs.get(left_dir)
        right_signal = inputs.get(right_dir)

        # A repeater is locked when either lateral neighbour sends STRONG (1).
        if ((left_signal  is not None and left_signal[0]  == SignalType.STRONG) or
            (right_signal is not None and right_signal[0] == SignalType.STRONG)):
            self.locked = True
        elif self.locked:
            self.locked = False

        if self.locked:
            # Hold current output while locked; re-emit so downstream stays updated.
            if self.output:
                outputs[output_dir] = (SignalType.STRONG, 15)
            return outputs if outputs else None

        self_ = array((0, 0, 0))

        # Rising edge — a new powered input arrived.
        if input_signal and input_signal[1] > 0 and self.count == 0:
            self.count = 1
            outputs[self_] = (SignalType.no_power, 0)   # schedule self-update
            return outputs

        # Counting up through the delay.
        if 0 < self.count < self.delay:
            self.count += 1
            outputs[self_] = (SignalType.no_power, 0)
            return outputs

        # Delay elapsed — turn output on and keep re-scheduling until input drops.
        if self.count >= self.delay:
            if input_signal and input_signal[1] > 0:
                self.count += 1
                self.output = True
                outputs[self_] = (SignalType.no_power, 0)
                outputs[output_dir] = (SignalType.STRONG, 15)
                return outputs
            else:
                self.count = 0
                if self.output:
                    self.output = False
                    outputs[output_dir] = (SignalType.no_power, 0)
                return outputs if outputs else None

        # No update needed.
        return None

    def __repr__(self):
        return (f'A{" locked " if self.locked else " "}Redstone Repeater '
                f'with state {"on" if self.output else "off"}')


# ---------------------------------------------------------------------------
# Comparator
# ---------------------------------------------------------------------------
class Comparator(Component):
    def __init__(self, position: ndarray, facing: str, mode: str = "compare", **kwargs):
        super().__init__(position)
        self.facing = facing
        self.mode = (mode == "subtract")   # True → subtract, False → compare
        self.output_strength = 0

    def update(self, inputs: SignalDict) -> SignalDict | None:
        output_dir      = translateDirection(self.facing)
        main_input_dir  = -1 * output_dir
        right           = rotateOffset90(main_input_dir)
        left            = rotateOffset90(output_dir)

        outputs = SignalDict()
        self_   = array((0, 0, 0))

        # If no rear input, there is nothing to propagate.
        rear_signal = inputs.get(main_input_dir)
        if rear_signal is None:
            return None
        rear = rear_signal[1]

        # Self-addressed tick — the delayed output is now ready to fire.
        if self_ in inputs:
            if self.output_strength > 0:
                outputs[output_dir] = (SignalType.STRONG, self.output_strength)
            return outputs if outputs else None

        # No side inputs → maintain (pass-through) mode.
        if right not in inputs and left not in inputs:
            if rear > 0:
                self.output_strength = rear
                outputs[self_] = (SignalType.STRONG, rear)   # delay via self
            return outputs if outputs else None

        left_val  = inputs[left][1]  if left  in inputs else 0
        right_val = inputs[right][1] if right in inputs else 0
        side_max  = max(left_val, right_val)

        def _compare() -> int:
            return rear if side_max < rear else 0

        def _subtract() -> int:
            return max(rear - side_max, 0)

        result = _subtract() if self.mode else _compare()
        self.output_strength = result

        if result > 0:
            outputs[self_] = (SignalType.STRONG, result)   # delay via self
        return outputs if outputs else None