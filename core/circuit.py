"""
circuit.py
==========
The Circuit class is the core model of the redstone simulator.
 
Architecture
------------
- Blocks are stored in a spatial dict keyed by ``tuple(position)`` for O(1)
  neighbour lookup via position arithmetic.
- The Circuit owns the tick scheduler.  Call ``circuit.step()`` once per
  game tick (20 Hz in real Minecraft).  Two consecutive game ticks form one
  *redstone tick*:
    - Even game tick  → OUTPUT phase  (each block produces its SignalDict)
    - Odd  game tick  → INPUT  phase  (pending SignalDicts are delivered)
- A ``pending`` queue accumulates (target_position_tuple, SignalDict) pairs
  produced during the output phase.  On the input phase those are merged
  into per-block ``SignalDict``s and delivered to each block's ``update()``.
 
Self-addressed outputs
----------------------
Some components (Repeater, Comparator) put the zero-offset ``array([0,0,0])``
key in their output to schedule a future update to themselves.  The circuit
detects this and re-queues the signal for the *same* block, meaning it arrives
on the *next* input tick — exactly one redstone tick of self-delay.
 
Signal merging
--------------
When multiple outputs target the same block from the same direction, the
circuit keeps the signal with the highest *priority* (lowest SignalType enum
value, i.e. STRONG beats weak) and, on ties, the highest strength.
"""
 
from __future__ import annotations
 
from collections import defaultdict
from typing import Iterator
 
from numpy import ndarray, array
 
from lib.base import Component, Block, Constant, SignalDict, SignalType, translateDirection
 
 
# Six cardinal neighbour offsets — used when a block wants to broadcast to
# all neighbours without specifying directions explicitly.
_CARDINALS: list[ndarray] = [
    array(( 1,  0,  0)), array((-1,  0,  0)),
    array(( 0,  1,  0)), array(( 0, -1,  0)),
    array(( 0,  0,  1)), array(( 0,  0, -1)),
]
 
# Type alias for the spatial-dict key
PosKey = tuple[int, int, int]
 
 
def _pos_key(pos: ndarray) -> PosKey:
    return (int(pos[0]), int(pos[1]), int(pos[2]))
 
 
def _merge_signals(
    base: SignalDict, incoming: SignalDict, from_offset: ndarray
) -> None:
    """
    Merge ``incoming`` (keyed by *relative* offsets from the *sender's*
    perspective) into ``base`` (keyed by offsets from the *receiver's*
    perspective).
 
    ``from_offset`` is ``sender.position - receiver.position``, i.e. the
    direction *from the receiver toward the sender*.
 
    Priority rule: lower SignalType enum value wins; ties broken by strength.
    """
    for sender_relative_dir in incoming:
        sig_type, strength = incoming[sender_relative_dir]
        # The key we store in the receiver's SignalDict is the offset pointing
        # FROM the receiver TO the sender — i.e. ``from_offset``.
        existing = base.get(from_offset)
        if existing is None:
            base[from_offset] = (sig_type, strength)
        else:
            ex_type, ex_strength = existing
            # Lower enum value = higher priority signal type
            if sig_type.value < ex_type.value:
                base[from_offset] = (sig_type, strength)
            elif sig_type.value == ex_type.value and strength > ex_strength:
                base[from_offset] = (sig_type, strength)
 
 
class Circuit:
    """
    Redstone circuit model.
 
    Parameters
    ----------
    blocks : list[Component]
        All blocks to register in the circuit.  Positions must be unique.
 
    Usage
    -----
    ::
 
        c = Circuit([lever, dust, lamp])
        c.step()   # game tick 0 — output phase  (initial broadcast)
        c.step()   # game tick 1 — input  phase  (signals delivered)
        c.step()   # game tick 2 — output phase  (blocks react)
        ...
    """
 
    def __init__(self, blocks: list[Component]):
        # Primary spatial registry: position tuple → block
        self._grid: dict[PosKey, Component] = {}
 
        # Pending signals accumulated during the OUTPUT phase.
        # Maps receiver position key → SignalDict (already in receiver-space).
        self._pending: dict[PosKey, SignalDict] = defaultdict(SignalDict)
 
        # Game-tick counter (starts at 0).
        self._tick: int = 0
 
        for block in blocks:
            self.register(block)
 
        # Seed the very first output phase so constant sources and other
        # always-on components fire on tick 0 without any external nudge.
        self._bootstrap()
 
    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
 
    def register(self, block: Component) -> None:
        """Add a block to the circuit.  Raises if the position is occupied."""
        key = _pos_key(block.position)
        if key in self._grid:
            raise ValueError(
                f"Position {block.position} is already occupied by "
                f"{self._grid[key]!r}"
            )
        self._grid[key] = block
 
    def remove(self, position: ndarray) -> Component:
        """Remove and return the block at *position*.  Raises KeyError if absent."""
        key = _pos_key(position)
        if key not in self._grid:
            raise KeyError(f"No block at {position}")
        return self._grid.pop(key)
 
    def get(self, position: ndarray) -> Component | None:
        """Return the block at *position*, or None."""
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
 
    def block_states(self) -> dict[PosKey, Component]:
        """Return a shallow copy of the spatial grid (for visualisation)."""
        return dict(self._grid)
 
    # ------------------------------------------------------------------
    # Tick machinery
    # ------------------------------------------------------------------
 
    def step(self) -> None:
        """
        Advance the simulation by one game tick.
 
        Even ticks → OUTPUT phase  (collect outputs, fill ``_pending``)
        Odd  ticks → INPUT  phase  (deliver pending signals, run updates)
        """
        if self._tick % 2 == 0:
            self._output_phase()
        else:
            self._input_phase()
        self._tick += 1
 
    def redstone_step(self) -> None:
        """
        Convenience: advance by a full redstone tick (two game ticks).
        Equivalent to calling ``step()`` twice.
        """
        self.step()
        self.step()
 
    # ------------------------------------------------------------------
    # Internal phases
    # ------------------------------------------------------------------
 
    def _bootstrap(self) -> None:
        """
        Ask every block for its initial output so that constant sources
        (RedstoneBlock, Lever already toggled on, etc.) seed the pending
        queue before the first real step.
 
        Blocks that carry state from construction (e.g. a Lever with
        ``state=True``) should return a non-None SignalDict from their
        ``update()`` when called with an empty SignalDict.  Constant blocks
        get special-cased here.
        """
        for block in self._grid.values():
            outputs = self._initial_output(block)
            if outputs:
                self._enqueue_outputs(block, outputs)
 
    def _initial_output(self, block: Component) -> SignalDict | None:
        """
        Ask a block for its initial (tick-0) output.
 
        ``Constant`` blocks always emit; other blocks are queried with an
        empty SignalDict to let them decide.
        """
        if isinstance(block, Constant):
            outputs = SignalDict()
            for d in _CARDINALS:
                outputs[d] = (SignalType.indirect, block.signal_strength)
            return outputs
 
        # For other blocks that accept inputs, call update with empty dict.
        # Blocks that are off by default will return None — that's fine.
        if hasattr(block, "update"):
            try:
                return block.update(SignalDict())
            except TypeError:
                # Some update() signatures don't accept inputs (e.g. Button
                # before it's pressed).  Ignore.
                return None
        return None
 
    def _output_phase(self) -> None:
        """
        OUTPUT phase (even ticks).
 
        Each block that has a pending self-addressed signal (from a previous
        input tick) or that is a spontaneous source fires its ``update()``,
        and the resulting outputs are enqueued into ``_pending``.
 
        In this phase we collect outputs from blocks that *already received*
        input last tick (tracked via ``_pending`` having an entry for them)
        **plus** any block that is self-driven (Constant, always-on source).
        """
        # Snapshot which blocks have pending inputs so we don't mutate while
        # iterating.
        active_keys = set(self._pending.keys())
 
        # Also include all Constant blocks — they always emit.
        for key, block in self._grid.items():
            if isinstance(block, Constant):
                active_keys.add(key)
 
        new_pending: dict[PosKey, SignalDict] = defaultdict(SignalDict)
 
        for key in active_keys:
            block = self._grid.get(key)
            if block is None:
                continue  # block was removed mid-simulation
 
            # Deliver pending inputs to the block
            inputs = self._pending.get(key, SignalDict())
            outputs = self._call_update(block, inputs)
 
            if outputs:
                self._enqueue_outputs_into(block, outputs, new_pending)
 
        # Replace pending with fresh outputs for the input phase
        self._pending = new_pending  # type: ignore[assignment]
 
    def _input_phase(self) -> None:
        """
        INPUT phase (odd ticks).
 
        Deliver the outputs collected during the output phase to their target
        blocks.  Each block's ``update()`` is called with the merged
        SignalDict of all signals arriving from neighbours.
 
        Any new outputs produced here are queued for the *next* output phase.
        """
        if not self._pending:
            return
 
        # Snapshot current pending and clear so blocks can re-queue.
        current_pending = self._pending
        self._pending = defaultdict(SignalDict)
 
        for key, inputs in current_pending.items():
            block = self._grid.get(key)
            if block is None:
                continue
 
            outputs = self._call_update(block, inputs)
            if outputs:
                self._enqueue_outputs(block, outputs)
 
    # ------------------------------------------------------------------
    # Output routing helpers
    # ------------------------------------------------------------------
 
    def _call_update(
        self, block: Component, inputs: SignalDict
    ) -> SignalDict | None:
        """
        Safely call a block's ``update()`` method.
 
        Handles the two common signatures:
          - ``update(inputs: SignalDict) -> SignalDict | None``   (most blocks)
          - ``update(initial_tick: bool = False) -> ...``         (RedstoneBlock)
          - ``update() -> ...``                                   (Button / spontaneous)
        """
        if not hasattr(block, "update"):
            return None
        try:
            result = block.update(inputs)
        except TypeError:
            # Signature doesn't accept inputs — try without.
            try:
                result = block.update()  # type: ignore[call-arg]
            except TypeError:
                result = None
        return result
 
    def _enqueue_outputs(
        self, sender: Component, outputs: SignalDict
    ) -> None:
        self._enqueue_outputs_into(sender, outputs, self._pending)
 
    def _enqueue_outputs_into(
        self,
        sender: Component,
        outputs: SignalDict,
        pending: dict[PosKey, SignalDict],
    ) -> None:
        """
        Translate a sender's output SignalDict (relative offsets) into
        absolute positions and merge into ``pending``.
 
        Self-addressed signals (offset == [0,0,0]) are re-queued for the
        *sender itself* — used by Repeater / Comparator for internal delay.
 
        Signals addressed to directions that have no registered block are
        silently dropped (open air).
        """
        self_offset_key = (0, 0, 0)
 
        for rel_dir in outputs:
            rel_key = tuple(int(x) for x in rel_dir)
            sig = outputs[rel_dir]
 
            if rel_key == self_offset_key:
                # Self-addressed: re-deliver to the sender next tick
                receiver_key = _pos_key(sender.position)
                # from_offset is zero for self-signals
                from_offset = array([0, 0, 0])
                existing = pending[receiver_key].get(from_offset)
                if existing is None:
                    pending[receiver_key][from_offset] = sig
                else:
                    # merge: lower type value wins, ties broken by strength
                    if sig[0].value < existing[0].value or (
                        sig[0].value == existing[0].value and sig[1] > existing[1]
                    ):
                        pending[receiver_key][from_offset] = sig
            else:
                # Absolute position of the target block
                target_pos = sender.position + rel_dir
                target_key = _pos_key(target_pos)
 
                if target_key not in self._grid:
                    continue  # no block there — drop signal
 
                # The offset *from the receiver* to the *sender*
                from_offset = sender.position - target_pos  # == -rel_dir
 
                receiver_sd = pending[target_key]
                existing = receiver_sd.get(from_offset)
                if existing is None:
                    receiver_sd[from_offset] = sig
                else:
                    if sig[0].value < existing[0].value or (
                        sig[0].value == existing[0].value and sig[1] > existing[1]
                    ):
                        receiver_sd[from_offset] = sig
 
    # ------------------------------------------------------------------
    # Debugging helpers
    # ------------------------------------------------------------------
 
    def dump(self) -> None:
        """Print a human-readable snapshot of the current circuit state."""
        print(f"=== Circuit snapshot  tick={self._tick} ===")
        for key in sorted(self._grid):
            block = self._grid[key]
            pending = self._pending.get(key)
            pending_str = f"  pending={pending}" if pending else ""
            print(f"  {key}: {block!r}{pending_str}")
        print()
 
    def pending_signals(self) -> dict[PosKey, SignalDict]:
        """Return a copy of the current pending signal queue."""
        return dict(self._pending)
 
