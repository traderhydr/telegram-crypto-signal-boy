"""Shared data models for signals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List


class Side(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


@dataclass
class Signal:
    symbol: str
    side: Side
    leverage: int
    entries: List[float]
    take_profits: List[float]
    stop_loss: float
    rationale: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    reference_price: float = 0.0
    fast_ema: float = 0.0
    slow_ema: float = 0.0
    rsi: float = 0.0

    def format_message(self) -> str:
        """Human-readable Telegram message body."""
        ts = self.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
        entry_lines = "\n".join(
            f"  Entry {i}: {price:.4f}" for i, price in enumerate(self.entries, start=1)
        )
        tp_lines = "\n".join(
            f"  TP{i}: {price:.4f}" for i, price in enumerate(self.take_profits, start=1)
        )
        return (
            f"🔔 {self.side.value} Signal — {self.symbol}\n"
            f"Leverage: {self.leverage}x\n"
            f"Ref price: {self.reference_price:.4f}\n"
            f"\nEntries:\n{entry_lines}\n"
            f"\nTake profits:\n{tp_lines}\n"
            f"\nStop loss: {self.stop_loss:.4f}\n"
            f"\nRationale: {self.rationale}\n"
            f"Time: {ts}"
        )
