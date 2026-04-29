from __future__ import annotations

from collections import defaultdict
from typing import Iterator

from numpy import ndarray, array

from lib.base import Component, Constant, SignalDict, SignalType


_CARDINALS: list[ndarray] = [
    array(( 1,  0,  0)), array((-1,  0,  0)),
    array(( 0,  1,  0)), array(( 0, -1,  0)),
    array(( 0,  0,  1)), array(( 0,  0, -1)),
]

PosKey = tuple[int, int, int]


def _pos_key(pos: ndarray) -> PosKey:
    return (int(pos[0]), int(pos[1]), int(pos[2]))


class Circuit:
    """
    Redstone circuit model.

    Params
    ----------
    blocks : list[Component]
        All blocks to register in the circuit. Positions must be unique.

    """

    def __init__(self, blocks: list[Component]):
        self._grid: dict[PosKey, Component] = {}
        self._pending: dict[PosKey, SignalDict] = defaultdict(SignalDict)
        self._tick: int = 0

        for block in blocks:
            self.register(block)

        self._bootstrap()


    def register(self, block: Component) -> None:
        key = _pos_key(block.position)
        if key in self._grid:
            raise ValueError(
                f"Position {block.position} is already occupied by {self._grid[key]!r}"
            )
        self._grid[key] = block




    def notify(self, block: Component) -> None:
        """
        Mark a block as active so the next step() calls its update().

        Must be called after every external state change:
            lever.toggle(); circuit.notify(lever)
            button.press();  circuit.notify(button)

        Inserts the block into _pending with an empty SignalDict if it isn't
        already there. Its update() will run on the next step() and route
        whatever its internal state now produces.
        """   
        key = _pos_key(block.position)
        if key not in self._grid:
            raise KeyError(f"Block {block!r} is not registered in this circuit.")
        if key not in self._pending:
            self._pending[key] = SignalDict()

    def remove(self, position: ndarray) -> Component:
        key = _pos_key(position)
        if key not in self._grid:
            raise KeyError(f"No block at {position}")
        return self._grid.pop(key)

    def get(self, position: ndarray) -> Component | None:
        return self._grid.get(_pos_key(position))

    def __iter__(self) -> Iterator[Component]:
        return iter(self._grid.values())

    def __len__(self) -> int:
        return len(self._grid)

    def __repr__(self) -> str:
        return (
            f"Circuit(tick={self._tick}, blocks={len(self._grid)}, "
            f"pending={len(self._pending)})"
        )

    @property
    def tick(self) -> int:
        return self._tick

    #For VPython
    def block_states(self) -> dict[PosKey, Component]:
        return dict(self._grid)


    def step(self) -> None:
        """
        Advance the simulation by one game tick.

        Deliver-and-react cycle:
          1. Snapshot + clear _pending.
          2. Call update() on every block that has incoming signals; route
             its outputs into fresh _pending for the next tick.
          3. Re-emit always-on sources (Constant, RedstoneBlock) every tick.
        """
        from lib.power import RedstoneBlock  # local import avoids circular

        # 1. Snapshot and clear
        inbox = self._pending
        self._pending = defaultdict(SignalDict)

        # 2. Deliver to blocks with pending signals
        for key, inputs in inbox.items():
            block = self._grid.get(key)
            if block is None:
                continue
            outputs = self._call_update(block, inputs)
            if outputs:
                self._enqueue_outputs(block, outputs)

        # 3. Always-on sources re-emit every tick
        for key, block in self._grid.items():
            if isinstance(block, (Constant, RedstoneBlock)):
                outputs = self._call_update(block, SignalDict())
                if outputs:
                    self._enqueue_outputs(block, outputs)
        

        self._tick += 1

    def redstone_step(self) -> None:
        self.step()
        self.step()

    

    def _bootstrap(self) -> None:
        """
        Seed _pending from always-on sources before the first step().

        Only autonomous sources emit at bootstrap:
        - Constant, RedstoneBlock   — always on
        - RedstoneTorch(state=True) — on by default

        Lever, Button, and passive blocks (Dust) are left silent until
        the user activates them via notify().
        """
        from lib.power import RedstoneBlock, RedstoneTorch

        for block in self._grid.values():
            outputs: SignalDict | None = None

            if isinstance(block, Constant):
                outputs = SignalDict()
                for d in _CARDINALS:
                    outputs[d] = (SignalType.indirect, block.signal_strength)

            elif isinstance(block, RedstoneBlock):
                outputs = self._call_update(block, SignalDict())

            elif isinstance(block, RedstoneTorch) and block.state:
                outputs = self._call_update(block, SignalDict())

            if outputs:
                self._enqueue_outputs(block, outputs)


    def _call_update(self, block: Component, inputs: SignalDict) -> SignalDict | None:
        if not hasattr(block, "update"):
            return None
        try:
            return block.update(inputs)  # type: ignore
        except TypeError:
            try:
                return block.update()  # type: ignore[call-arg]
            except TypeError:
                return None

    
    def _enqueue_outputs(self, sender: Component, outputs: SignalDict) -> None:
        self_offset_key = (0, 0, 0)

        for rel_dir in outputs:
            rel_key = tuple(int(x) for x in rel_dir)
            sig = outputs[rel_dir]

            if rel_key == self_offset_key:
                # Self-addressed — re-deliver to the sender on the next tick.
                # Used by Repeater/Comparator for internal delay.
                receiver_key = _pos_key(sender.position)
                from_offset = array([0, 0, 0])
                self._merge_into(self._pending[receiver_key], from_offset, sig)
            else:
                target_pos = sender.position + rel_dir
                target_key = _pos_key(target_pos)

                if target_key not in self._grid:
                    continue  #ignore

                #Key in **receiver-space**: direction FROM receiver TO sender
                from_offset = sender.position - target_pos  # == -rel_dir
                self._merge_into(self._pending[target_key], from_offset, sig)

    @staticmethod
    def _merge_into(
        sd: SignalDict, from_offset: ndarray, sig: tuple[SignalType, int]
    ) -> None:
        
        #Write sig into sd[from_offset], keeping the higher-priority signal.
        #Lower SignalType enum value = higher priority. Ties broken by strength.
        
        existing = sd.get(from_offset)
        if existing is None:
            sd[from_offset] = sig
        else:
            ex_type, ex_strength = existing
            new_type, new_strength = sig
            if new_type.value < ex_type.value:
                sd[from_offset] = sig
            elif new_type.value == ex_type.value and new_strength > ex_strength:
                sd[from_offset] = sig

    #debugging stuff
    def dump(self) -> None:
        #Print snapshot of current block states and pending signals
        print(f"=== Circuit snapshot  tick={self._tick} ===")
        for key in sorted(self._grid):
            block = self._grid[key]
            pending = self._pending.get(key)
            pending_str = f"  pending={pending}" if pending else ""
            print(f"  {key}: {block!r}{pending_str}")
        print()

    def pending_signals(self) -> dict[PosKey, SignalDict]:
        return dict(self._pending)