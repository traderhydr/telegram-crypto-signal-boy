"""Supertrend and higher-timeframe EMA bias / resample helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from .indicators import atr, ema, last_valid

# ---------------------------------------------------------------------------
# Supertrend (ATR-based) + higher-timeframe EMA bias helpers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SupertrendPoint:
    """Supertrend line value and direction at one bar."""

    value: float
    direction: int  # +1 = bullish (price above ST), -1 = bearish (below)


def supertrend(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 10,
    multiplier: float = 3.0,
) -> List[Optional[SupertrendPoint]]:
    """
    ATR-based Supertrend (TradingView-style).

    Defaults: period=10, multiplier=3.0.
    First valid point appears once ATR(period) is available (index `period`).
    direction +1 => close is (or flipped to) above the lower band (bullish).
    direction -1 => close is below the upper band (bearish).
    """
    if period < 1:
        raise ValueError("Supertrend period must be >= 1")
    if multiplier <= 0:
        raise ValueError("Supertrend multiplier must be > 0")
    n = len(closes)
    if not (len(highs) == len(lows) == n):
        raise ValueError("highs, lows, closes must be same length")

    atr_series = atr(highs, lows, closes, period)
    out: List[Optional[SupertrendPoint]] = [None] * n
    final_upper: List[Optional[float]] = [None] * n
    final_lower: List[Optional[float]] = [None] * n
    direction: List[int] = [0] * n

    for i in range(n):
        a = atr_series[i]
        if a is None:
            continue
        hl2 = (highs[i] + lows[i]) / 2.0
        basic_upper = hl2 + multiplier * a
        basic_lower = hl2 - multiplier * a

        prev_fu = final_upper[i - 1] if i > 0 else None
        prev_fl = final_lower[i - 1] if i > 0 else None
        prev_close = closes[i - 1] if i > 0 else closes[i]

        if prev_fu is None:
            final_upper[i] = basic_upper
        else:
            if basic_upper < prev_fu or prev_close > prev_fu:
                final_upper[i] = basic_upper
            else:
                final_upper[i] = prev_fu

        if prev_fl is None:
            final_lower[i] = basic_lower
        else:
            if basic_lower > prev_fl or prev_close < prev_fl:
                final_lower[i] = basic_lower
            else:
                final_lower[i] = prev_fl

        assert final_upper[i] is not None and final_lower[i] is not None
        prev_dir = direction[i - 1] if i > 0 and direction[i - 1] != 0 else 1
        prev_fu_for_flip = prev_fu if prev_fu is not None else final_upper[i]
        prev_fl_for_flip = prev_fl if prev_fl is not None else final_lower[i]

        if prev_dir == 1:
            # Was bullish; flip to bearish if close crosses below prior lower band
            if closes[i] < prev_fl_for_flip:
                direction[i] = -1
            else:
                direction[i] = 1
        else:
            # Was bearish; flip to bullish if close crosses above prior upper band
            if closes[i] > prev_fu_for_flip:
                direction[i] = 1
            else:
                direction[i] = -1

        st_val = final_lower[i] if direction[i] == 1 else final_upper[i]
        assert st_val is not None
        out[i] = SupertrendPoint(value=st_val, direction=direction[i])

    return out


def supertrend_agrees(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    side_long: bool,
    period: int = 10,
    multiplier: float = 3.0,
) -> Tuple[bool, str]:
    """
    LONG only if Supertrend direction is bullish (price above ST);
    SHORT only if bearish (price below ST).
    """
    series = supertrend(highs, lows, closes, period=period, multiplier=multiplier)
    point = last_valid(series)
    if point is None:
        return False, "insufficient Supertrend data"
    bullish = point.direction > 0
    price = closes[-1]
    if side_long and not bullish:
        return (
            False,
            f"Supertrend bearish (ST={point.value:.4f}, price={price:.4f})",
        )
    if (not side_long) and bullish:
        return (
            False,
            f"Supertrend bullish (ST={point.value:.4f}, price={price:.4f})",
        )
    side = "bull" if bullish else "bear"
    return True, f"Supertrend {side} ST={point.value:.4f}"


def htf_ema_bias(
    htf_closes: Sequence[float],
    side_long: bool,
    fast: int = 20,
    slow: int = 50,
) -> Tuple[bool, str]:
    """
    Higher-timeframe EMA bias gate.

    LONG requires HTF EMA(fast) > EMA(slow); SHORT requires EMA(fast) < EMA(slow).
    Default fast/slow = 20/50 (documented HTF bias pair on 4h).
    """
    if fast < 1 or slow < 1:
        raise ValueError("HTF EMA periods must be >= 1")
    if fast >= slow:
        raise ValueError("HTF EMA fast must be < slow")
    if len(htf_closes) < slow:
        return (
            False,
            f"insufficient HTF data ({len(htf_closes)} bars < EMA{slow})",
        )
    fast_s = ema(htf_closes, fast)
    slow_s = ema(htf_closes, slow)
    f = last_valid(fast_s)
    s = last_valid(slow_s)
    if f is None or s is None:
        return False, "insufficient HTF EMA data"
    bullish = f > s
    if side_long and not bullish:
        return (
            False,
            f"HTF bearish EMA{fast}={f:.4f}<=EMA{slow}={s:.4f}",
        )
    if (not side_long) and bullish:
        return (
            False,
            f"HTF bullish EMA{fast}={f:.4f}>=EMA{slow}={s:.4f}",
        )
    bias = "bull" if bullish else "bear"
    return True, f"HTF {bias} EMA{fast}={f:.4f} EMA{slow}={s:.4f}"


def resample_klines_to_htf(
    candles: Sequence[dict],
    htf_ms: int,
) -> List[dict]:
    """
    Aggregate LTF OHLCV candles into higher-timeframe buckets aligned to
    epoch multiples of ``htf_ms`` (Binance-style UTC boundaries).

    Each output candle has open/high/low/close/volume/open_time/close_time.
    Incomplete trailing bucket is included; callers must drop it when its
    close_time is still in the future relative to the evaluation bar.
    """
    if htf_ms <= 0:
        raise ValueError("htf_ms must be > 0")
    if not candles:
        return []

    buckets: dict = {}
    order: List[int] = []
    for c in candles:
        ot = int(c["open_time"])
        bucket = (ot // htf_ms) * htf_ms
        if bucket not in buckets:
            buckets[bucket] = {
                "open_time": bucket,
                "close_time": bucket + htf_ms - 1,
                "open": float(c["open"]),
                "high": float(c["high"]),
                "low": float(c["low"]),
                "close": float(c["close"]),
                "volume": float(c.get("volume", 0.0)),
            }
            order.append(bucket)
        else:
            b = buckets[bucket]
            b["high"] = max(b["high"], float(c["high"]))
            b["low"] = min(b["low"], float(c["low"]))
            b["close"] = float(c["close"])
            b["volume"] += float(c.get("volume", 0.0))
    return [buckets[k] for k in order]


def completed_htf_closes(
    htf_candles: Sequence[dict],
    asof_close_time_ms: int,
) -> List[float]:
    """Return closes of HTF candles that have fully closed by ``asof_close_time_ms``."""
    return [
        float(c["close"])
        for c in htf_candles
        if int(c["close_time"]) <= int(asof_close_time_ms)
    ]
