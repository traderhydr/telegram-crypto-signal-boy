"""Volume helpers: relative volume, OBV, volume-price agreement (pure Python).

These are pragmatic filters — not a full volume-profile / footprint suite.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple


def sma(values: Sequence[float], period: int) -> List[Optional[float]]:
    """Simple moving average; first valid at index period-1."""
    if period < 1:
        raise ValueError("period must be >= 1")
    n = len(values)
    out: List[Optional[float]] = [None] * n
    if n < period:
        return out
    window = sum(values[:period])
    out[period - 1] = window / period
    for i in range(period, n):
        window += values[i] - values[i - period]
        out[i] = window / period
    return out


def relative_volume(
    volumes: Sequence[float], period: int = 20
) -> List[Optional[float]]:
    """
    vol[i] / SMA(vol, period)[i].

    None until SMA is defined or when SMA is 0.
    """
    avg = sma(volumes, period)
    out: List[Optional[float]] = [None] * len(volumes)
    for i, a in enumerate(avg):
        if a is None or a <= 0:
            continue
        out[i] = volumes[i] / a
    return out


def volume_ratio_ok(
    volumes: Sequence[float],
    period: int = 20,
    min_ratio: float = 1.2,
    confirm_bars: int = 1,
) -> Tuple[bool, str]:
    """
    Require relative volume >= min_ratio on the signal bar or any of the
    last `confirm_bars` bars (inclusive of current).

    confirm_bars=1 -> only the current (last) bar.
    """
    if confirm_bars < 1:
        raise ValueError("confirm_bars must be >= 1")
    ratios = relative_volume(volumes, period)
    n = len(ratios)
    if n == 0:
        return False, "volume: no data"
    start = max(0, n - confirm_bars)
    best_i = -1
    best_r: Optional[float] = None
    for i in range(start, n):
        r = ratios[i]
        if r is None:
            continue
        if best_r is None or r > best_r:
            best_r = r
            best_i = i
    if best_r is None:
        return False, f"volume: insufficient SMA({period}) data"
    if best_r < min_ratio:
        return (
            False,
            f"volume: rel_vol={best_r:.2f}<{min_ratio} "
            f"(SMA{period}; checked last {confirm_bars} bar(s))",
        )
    offset = n - 1 - best_i
    where = "signal bar" if offset == 0 else f"{offset} bar(s) ago"
    return True, f"rel_vol={best_r:.2f}>={min_ratio} ({where}, SMA{period})"


def obv(closes: Sequence[float], volumes: Sequence[float]) -> List[float]:
    """On-Balance Volume (cumulative). Length matches closes."""
    n = len(closes)
    if len(volumes) != n:
        raise ValueError("closes and volumes must be same length")
    out = [0.0] * n
    if n == 0:
        return out
    out[0] = float(volumes[0])
    for i in range(1, n):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def obv_slope(obv_series: Sequence[float], lookback: int = 5) -> Optional[float]:
    """
    Simple slope: (OBV[-1] - OBV[-1-lookback]) / lookback.
    Positive = rising OBV.
    """
    if lookback < 1:
        raise ValueError("lookback must be >= 1")
    n = len(obv_series)
    if n <= lookback:
        return None
    return (obv_series[-1] - obv_series[-1 - lookback]) / lookback


def volume_price_agreement(
    closes: Sequence[float],
    volumes: Sequence[float],
    side_long: bool,
    obv_lookback: int = 5,
) -> Tuple[bool, str]:
    """
    Lightweight volume-price agreement via OBV slope.

    LONG: prefer rising OBV (slope > 0) — not collapsing on up moves.
    SHORT: prefer falling OBV (slope < 0).

    Also flags collapsing volume on a directional close vs prior bar when OBV
    slope is flat/wrong-way (extra guardrail when last bar is with-trend).
    """
    if len(closes) < 2 or len(volumes) != len(closes):
        return False, "obv: insufficient data"
    series = obv(closes, volumes)
    slope = obv_slope(series, obv_lookback)
    if slope is None:
        return False, f"obv: need >{obv_lookback} bars"

    last_up = closes[-1] > closes[-2]
    last_down = closes[-1] < closes[-2]
    # Collapsing volume = last bar volume well below prior bar
    vol_collapse = volumes[-1] < volumes[-2] * 0.5 if volumes[-2] > 0 else False

    if side_long:
        if slope <= 0:
            return (
                False,
                f"obv: slope={slope:.4f}<=0 (want rising for LONG, lb={obv_lookback})",
            )
        if last_up and vol_collapse:
            return False, "obv: volume collapsing on up-close (LONG)"
        return True, f"obv: slope={slope:.4f}>0 (bullish agreement)"
    else:
        if slope >= 0:
            return (
                False,
                f"obv: slope={slope:.4f}>=0 (want falling for SHORT, lb={obv_lookback})",
            )
        if last_down and vol_collapse:
            return False, "obv: volume collapsing on down-close (SHORT)"
        return True, f"obv: slope={slope:.4f}<0 (bearish agreement)"
