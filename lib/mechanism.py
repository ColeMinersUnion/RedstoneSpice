from lib.base import Component, SignalType, SignalDict
from numpy import ndarray, array

directions = [
    array(( 1,  0,  0)), array((-1,  0,  0)),
    array(( 0,  1,  0)), array(( 0, -1,  0)),
    array(( 0,  0,  1)), array(( 0,  0, -1)),
]


class ReadableComponent(Component):
    """Base class for mechanisms that can be read by comparators."""
    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)

    def comparator_output(self) -> int:
        """Override in subclasses to expose a signal strength to comparators."""
        return 0


# ---------------------------------------------------------------------------
# RedstoneLamp — purely reflects the incoming signal.
# On  while any powering signal is present; off the moment all signals drop.
# Emits indirect power to all adjacent solid blocks when lit.
# ---------------------------------------------------------------------------
class RedstoneLamp(Component):
    """
    Turns on whenever any adjacent block delivers a powering signal
    (STRONG / strong / WEAK / weak / indirect).  The lamp itself is
    transparent to redstone, so it never propagates signal further — it
    only emits SignalType.indirect outward so that adjacent solid blocks
    know they're next to a lit lamp (required for correct Block update logic).

    Wiki: https://minecraft.wiki/w/Redstone_Lamp
    """

    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)
        self.lit = kwargs.get("lit", False)
        self.transparent = True          # lamps don't conduct redstone

    def _is_powering(self, signal: tuple[SignalType, int]) -> bool:
        sig_type, strength = signal
        return sig_type != SignalType.no_power and strength > 0

    def update(self, inputs: SignalDict) -> SignalDict | None:
        prev = self.lit
        self.lit = any(self._is_powering(inputs[k]) for k in inputs)

        # Only emit an update when state changes, to avoid noisy propagation.
        if self.lit == prev:
            return None

        outputs = SignalDict()
        if self.lit:
            for d in directions:
                outputs[d] = (SignalType.indirect, 15)
        else:
            # Broadcast a zero-strength indirect signal so neighbors know
            # the lamp went dark and can re-evaluate their own state.
            for d in directions:
                outputs[d] = (SignalType.no_power, 0)
        return outputs

    def __repr__(self):
        return f"RedstoneLamp({'lit' if self.lit else 'unlit'}) at {self.position}"


# ---------------------------------------------------------------------------
# NoteBlock — impulse response.
# Plays exactly once on the rising edge of the input signal.
# Never powers adjacent blocks (purely an output device in this sim).
# ---------------------------------------------------------------------------
class NoteBlock(Component):
    """
    Wiki: https://minecraft.wiki/w/Note_Block
    """

    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)
        self.powered = False   # tracks whether signal was high last tick
        self.played  = False   # prevents re-triggering while held high

    def _is_powering(self, signal: tuple[SignalType, int]) -> bool:
        sig_type, strength = signal
        return sig_type != SignalType.no_power and strength > 0

    def update(self, inputs: SignalDict) -> SignalDict | None:
        currently_powered = any(self._is_powering(inputs[k]) for k in inputs)

        outputs = SignalDict()

        # Rising edge — first tick of power
        if currently_powered and not self.powered:
            self.played  = True
            self.powered = True
            print(f"[NoteBlock @ {self.position}] *PLING*")
            # Brief indirect pulse so adjacent solid blocks get the update
            for d in directions:
                outputs[d] = (SignalType.indirect, 15)
            return outputs

        # Signal dropped — reset so next rising edge will fire again
        if not currently_powered and self.powered:
            self.powered = False
            self.played  = False
            for d in directions:
                outputs[d] = (SignalType.no_power, 0)
            return outputs

        # Held high (no change) or held low (no change) — nothing to do
        return None

    def __repr__(self):
        return f"NoteBlock({'powered' if self.powered else 'idle'}) at {self.position}"


# ---------------------------------------------------------------------------
# CopperBulb — latching memory element.
# Toggles its stored state on each rising edge; ignores sustained signals.
# Always emits indirect power to adjacent solid blocks based on current state.
# ---------------------------------------------------------------------------
class CopperBulb(ReadableComponent):
    """
    State toggles on every rising edge (low→high transition) of the input
    signal.  The bulb *retains* its state when the signal drops — this is
    the key property that makes it useful for memory circuits.

    The comparator output is 15 when lit, 0 when dark.

    Wiki: https://minecraft.wiki/w/Copper_Bulb
    """

    def __init__(self, position: ndarray, **kwargs):
        super().__init__(position)
        self.lit      = kwargs.get("lit", False)
        self.powered  = False   # tracks last-tick signal state

    def comparator_output(self) -> int:
        return 15 if self.lit else 0

    def _is_powering(self, signal: tuple[SignalType, int]) -> bool:
        sig_type, strength = signal
        return sig_type != SignalType.no_power and strength > 0

    def update(self, inputs: SignalDict) -> SignalDict | None:
        currently_powered = any(self._is_powering(inputs[k]) for k in inputs)

        outputs = SignalDict()

        # Rising edge only — toggle the stored state
        if currently_powered and not self.powered:
            self.powered = True
            self.lit = not self.lit
            # Broadcast new state to adjacent blocks
            sig = (SignalType.indirect, 15) if self.lit else (SignalType.no_power, 0)
            for d in directions:
                outputs[d] = sig
            return outputs

        # Track the falling edge so the next rising edge is detected correctly
        if not currently_powered and self.powered:
            self.powered = False
            # No state change — no output needed
            return None

        return None

    def __repr__(self):
        return (
            f"CopperBulb({'lit' if self.lit else 'dark'}, "
            f"{'powered' if self.powered else 'unpowered'}) at {self.position}"
        )
