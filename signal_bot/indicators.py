"""Technical indicators: EMA and RSI (pure Python, no network)."""

from __future__ import annotations

from typing import List, Optional, Sequence


def ema(values: Sequence[float], period: int) -> List[Optional[float]]:
    """
    Exponential moving average.
    Returns a list the same length as values; early indices are None until
    the SMA seed is available (index period-1).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n < period:
        return out

    seed = sum(values[:period]) / period
    out[period - 1] = seed
    mult = 2.0 / (period + 1)
    prev = seed
    for i in range(period, n):
        prev = (values[i] - prev) * mult + prev
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> List[Optional[float]]:
    """
    Wilder RSI.
    Returns None until enough bars exist (first valid at index `period`).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change

    avg_gain = gains / period
    avg_loss = losses / period

    def _rsi(ag: float, al: float) -> float:
        if al == 0:
            return 100.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = _rsi(avg_gain, avg_loss)

    for i in range(period + 1, n):
        change = values[i] - values[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi(avg_gain, avg_loss)

    return out


def last_valid(series: Sequence[Optional[float]]) -> Optional[float]:
    """Return the last non-None value, or None."""
    for v in reversed(series):
        if v is not None:
            return v
    return None
