"""Technical indicators: EMA, RSI, MACD, ATR, ADX, Fibonacci helpers (pure Python)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


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


def true_range(
    highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]
) -> List[Optional[float]]:
    """True range series; index 0 is None (needs prior close)."""
    n = len(closes)
    if not (len(highs) == len(lows) == n):
        raise ValueError("highs, lows, closes must be same length")
    out: List[Optional[float]] = [None] * n
    for i in range(1, n):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        out[i] = max(hl, hc, lc)
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[Optional[float]]:
    """
    Wilder ATR.
    First valid value at index `period` (needs `period` true-range samples
    from bars 1..period).
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    tr = true_range(highs, lows, closes)
    n = len(tr)
    out: List[Optional[float]] = [None] * n
    # Need TR at indices 1..period inclusive -> period samples
    if n <= period:
        return out
    seed_vals = [tr[i] for i in range(1, period + 1)]
    if any(v is None for v in seed_vals):
        return out
    prev = sum(seed_vals) / period  # type: ignore[arg-type]
    out[period] = prev
    for i in range(period + 1, n):
        assert tr[i] is not None
        prev = (prev * (period - 1) + tr[i]) / period  # type: ignore[operator]
        out[i] = prev
    return out


@dataclass(frozen=True)
class MacdPoint:
    macd: float
    signal: float
    histogram: float


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> List[Optional[MacdPoint]]:
    """
    Standard MACD (EMA fast - EMA slow) with signal EMA of the MACD line.
    First possible MACD at index slow-1; first signal after signal_period
    MACD samples (index slow-2+signal_period).
    """
    if fast < 1 or slow < 1 or signal_period < 1:
        raise ValueError("MACD periods must be >= 1")
    if fast >= slow:
        raise ValueError("MACD fast must be < slow")
    n = len(values)
    out: List[Optional[MacdPoint]] = [None] * n
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)

    macd_line: List[Optional[float]] = [None] * n
    for i in range(n):
        if fast_ema[i] is not None and slow_ema[i] is not None:
            macd_line[i] = fast_ema[i] - slow_ema[i]  # type: ignore[operator]

    # Signal = EMA of macd_line over non-None contiguous tail starting at slow-1
    first_macd = slow - 1
    if n <= first_macd:
        return out

    # Collect macd values from first_macd onward for EMA seeding
    signal_series: List[Optional[float]] = [None] * n
    # Seed when we have `signal_period` macd values
    if n - first_macd < signal_period:
        return out
    seed_end = first_macd + signal_period  # exclusive end index for seed window
    seed = sum(macd_line[i] for i in range(first_macd, seed_end)) / signal_period  # type: ignore[arg-type]
    signal_series[seed_end - 1] = seed
    mult = 2.0 / (signal_period + 1)
    prev = seed
    for i in range(seed_end, n):
        m = macd_line[i]
        assert m is not None
        prev = (m - prev) * mult + prev
        signal_series[i] = prev

    for i in range(n):
        m = macd_line[i]
        s = signal_series[i]
        if m is not None and s is not None:
            out[i] = MacdPoint(macd=m, signal=s, histogram=m - s)
    return out


def _wilder_smooth(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Wilder smoothing (RMA): seed = SMA, then prev*(n-1)+x / n."""
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, n):
        prev = (prev * (period - 1) + values[i]) / period
        out[i] = prev
    return out


def adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[Optional[float]]:
    """
    Wilder ADX.
    First meaningful ADX appears after ~2*period bars of directional data.
    """
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(closes)
    if not (len(highs) == len(lows) == n):
        raise ValueError("highs, lows, closes must be same length")
    out: List[Optional[float]] = [None] * n
    if n < period + 2:
        return out

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr_vals = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i - 1])
        lc = abs(lows[i] - closes[i - 1])
        tr_vals[i] = max(hl, hc, lc)

    # Smooth starting from index 1.. ; use Wilder on the series from 1
    # Align: build arrays of length n with zeros at 0, smooth full arrays
    # Standard approach: first smoothed value at index `period` using sum of
    # bars 1..period
    if n <= period:
        return out

    atr_s = [0.0] * n
    plus_s = [0.0] * n
    minus_s = [0.0] * n
    atr_s[period] = sum(tr_vals[1 : period + 1])
    plus_s[period] = sum(plus_dm[1 : period + 1])
    minus_s[period] = sum(minus_dm[1 : period + 1])
    for i in range(period + 1, n):
        atr_s[i] = atr_s[i - 1] - (atr_s[i - 1] / period) + tr_vals[i]
        plus_s[i] = plus_s[i - 1] - (plus_s[i - 1] / period) + plus_dm[i]
        minus_s[i] = minus_s[i - 1] - (minus_s[i - 1] / period) + minus_dm[i]

    dx = [0.0] * n
    for i in range(period, n):
        if atr_s[i] == 0:
            dx[i] = 0.0
            continue
        pdi = 100.0 * plus_s[i] / atr_s[i]
        mdi = 100.0 * minus_s[i] / atr_s[i]
        denom = pdi + mdi
        dx[i] = 0.0 if denom == 0 else 100.0 * abs(pdi - mdi) / denom

    # ADX = Wilder smooth of DX; first ADX at index 2*period - 1
    first_dx = period
    adx_start = first_dx + period - 1  # inclusive index of first ADX
    if n <= adx_start:
        return out
    seed = sum(dx[first_dx : first_dx + period]) / period
    out[adx_start] = seed
    prev = seed
    for i in range(adx_start + 1, n):
        prev = (prev * (period - 1) + dx[i]) / period
        out[i] = prev
    return out


# Default Fibonacci retracement ratios for confluence (prior best set).
# Override via Config.fib_levels / env FIB_LEVELS.
FIB_RATIOS: Tuple[float, ...] = (0.382, 0.5, 0.618)


@dataclass(frozen=True)
class FibSwing:
    """
    Swing used for Fib confluence.

    Upswing (bullish structure): swing_low -> swing_high (low index < high index).
      Retracement supports = high - ratio * (high - low) for ratio in FIB_RATIOS.
      LONG wants price near one of these supports (pullback into 0.382-0.618).

    Downswing (bearish structure): swing_high -> swing_low (high index < low index).
      Retracement resistances = low + ratio * (high - low) for ratio in FIB_RATIOS.
      SHORT wants price near one of these resistances (bounce into 0.382-0.618).
    """

    swing_high: float
    swing_low: float
    high_index: int
    low_index: int
    is_upswing: bool  # True if low precedes high in the lookback window

    @property
    def range(self) -> float:
        return self.swing_high - self.swing_low

    def retracement_levels(
        self, ratios: Optional[Sequence[float]] = None
    ) -> List[Tuple[float, float]]:
        """Return [(ratio, price), ...] for configured Fib ratios of this swing."""
        use = tuple(ratios) if ratios is not None else FIB_RATIOS
        rng = self.range
        if rng <= 0:
            return []
        levels: List[Tuple[float, float]] = []
        for r in use:
            if self.is_upswing:
                # Pullback from high toward low
                price = self.swing_high - r * rng
            else:
                # Bounce from low toward high
                price = self.swing_low + r * rng
            levels.append((r, price))
        return levels


def find_swing(
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int,
) -> Optional[FibSwing]:
    """
    Detect the dominant swing in the last `lookback` bars (including the
    current bar).

    Rules:
    - Window = last min(lookback, n) bars.
    - swing_high = max(high) in window; swing_low = min(low) in window.
    - If the low occurs *before* the high -> upswing (prior up move).
    - If the high occurs *before* the low -> downswing (prior down move).
    - If they share the same bar index, return None (degenerate).
    - Require a non-zero range.
    """
    n = len(highs)
    if len(lows) != n:
        raise ValueError("highs and lows must be same length")
    if lookback < 5 or n < 5:
        return None
    start = max(0, n - lookback)
    window_highs = highs[start:]
    window_lows = lows[start:]
    if not window_highs:
        return None

    rel_high_i = max(range(len(window_highs)), key=lambda i: window_highs[i])
    rel_low_i = min(range(len(window_lows)), key=lambda i: window_lows[i])
    high_index = start + rel_high_i
    low_index = start + rel_low_i
    swing_high = highs[high_index]
    swing_low = lows[low_index]
    if swing_high <= swing_low:
        return None
    if high_index == low_index:
        return None
    is_upswing = low_index < high_index
    return FibSwing(
        swing_high=swing_high,
        swing_low=swing_low,
        high_index=high_index,
        low_index=low_index,
        is_upswing=is_upswing,
    )


def fib_confluence(
    price: float,
    side_long: bool,
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int,
    tolerance: float,
    ratios: Optional[Sequence[float]] = None,
) -> Tuple[bool, str]:
    """
    Check whether `price` is within `tolerance` (absolute price units) of a
    Fib retracement level that fits the trade side.

    LONG: require an upswing in the lookback and price near a configured Fib
          support of that up move (default 0.382 / 0.5 / 0.618 pullback).
    SHORT: require a downswing and price near a configured Fib resistance of
           that down move (default 0.382 / 0.5 / 0.618 bounce).

    `ratios` overrides the module default FIB_RATIOS when provided.

    Returns (ok, detail_reason).
    """
    swing = find_swing(highs, lows, lookback)
    if swing is None:
        return False, "no valid Fib swing in lookback"

    if side_long and not swing.is_upswing:
        return (
            False,
            f"Fib structure is downswing (need upswing for LONG); "
            f"H={swing.swing_high:.4f}@{swing.high_index} "
            f"L={swing.swing_low:.4f}@{swing.low_index}",
        )
    if (not side_long) and swing.is_upswing:
        return (
            False,
            f"Fib structure is upswing (need downswing for SHORT); "
            f"H={swing.swing_high:.4f}@{swing.high_index} "
            f"L={swing.swing_low:.4f}@{swing.low_index}",
        )

    levels = swing.retracement_levels(ratios)
    if not levels:
        return False, "Fib range is zero"

    best_r, best_level, best_dist = levels[0][0], levels[0][1], abs(price - levels[0][1])
    for r, lvl in levels[1:]:
        d = abs(price - lvl)
        if d < best_dist:
            best_r, best_level, best_dist = r, lvl, d

    if best_dist <= tolerance:
        kind = "support" if side_long else "resistance"
        return (
            True,
            f"near Fib {best_r:.3f} {kind}={best_level:.4f} "
            f"(dist={best_dist:.4f}<=tol={tolerance:.4f}; "
            f"{'up' if swing.is_upswing else 'down'}swing "
            f"H={swing.swing_high:.4f} L={swing.swing_low:.4f})",
        )

    kind = "support" if side_long else "resistance"
    return (
        False,
        f"price {price:.4f} not near Fib {kind}s "
        f"(closest {best_r:.3f}={best_level:.4f}, dist={best_dist:.4f}>tol={tolerance:.4f})",
    )
