"""Entry ladder, take-profit, and stop-loss level generation."""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .models import Side


def generate_levels(
    reference_price: float,
    side: Side,
    entry_offsets_pct: Sequence[float],
    tp_targets_pct: Sequence[float],
    sl_beyond_ladder_pct: float,
) -> Tuple[List[float], List[float], float]:
    """
    Build 4 entries, 5 TPs, and 1 SL from a reference price.

    Entry offsets are interpreted relative to direction:
      LONG  — offsets applied as written (typically 0 / negative = dips)
      SHORT — offsets are mirrored (sign flipped) so dips become rips

    TP targets are % away from reference in the profitable direction.
    SL sits `sl_beyond_ladder_pct` beyond the farthest entry of the ladder.
    """
    if reference_price <= 0:
        raise ValueError("reference_price must be positive")
    if len(entry_offsets_pct) != 4:
        raise ValueError("entry_offsets_pct must have exactly 4 values")
    if len(tp_targets_pct) != 5:
        raise ValueError("tp_targets_pct must have exactly 5 values")

    sign = 1.0 if side == Side.LONG else -1.0

    # Entries
    entries: List[float] = []
    for off in entry_offsets_pct:
        # For SHORT, mirror the offset sign so the same config works both ways
        applied = off if side == Side.LONG else -off
        entries.append(round(reference_price * (1.0 + applied / 100.0), 8))

    # Take profits in profit direction
    take_profits: List[float] = []
    for tp in tp_targets_pct:
        take_profits.append(
            round(reference_price * (1.0 + sign * tp / 100.0), 8)
        )

    # Farthest entry = worst fill on the ladder (most adverse)
    if side == Side.LONG:
        farthest = min(entries)
        stop_loss = round(farthest * (1.0 - sl_beyond_ladder_pct / 100.0), 8)
    else:
        farthest = max(entries)
        stop_loss = round(farthest * (1.0 + sl_beyond_ladder_pct / 100.0), 8)

    return entries, take_profits, stop_loss
