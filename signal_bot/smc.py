"""Practical Smart Money Concepts (SMC) approximations (pure Python).

NOT a TradingView SMC clone. Definitions are intentionally simple and
testable so they can gate signals without fragile fractal heuristics.

Core (FILTER_SMC):
  1. Market structure — swing highs/lows + Break of Structure (BOS)
  2. Fair Value Gap (FVG) — 3-candle imbalance interaction

Optional (FILTER_SMC_OB):
  3. Order block — last opposing candle before the impulsive BOS move
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class SwingPoint:
    index: int
    price: float
    kind: str  # "high" | "low"


@dataclass(frozen=True)
class StructureEvent:
    """A BOS event: close broke a prior swing in the given direction."""

    index: int  # bar where break was confirmed (close)
    broken_swing: SwingPoint
    bullish: bool  # True = broke swing high; False = broke swing low


@dataclass(frozen=True)
class FairValueGap:
    """3-candle imbalance zone.

    Bullish FVG: candle[i-2].high < candle[i].low  (gap up; support zone)
    Bearish FVG: candle[i-2].low > candle[i].high  (gap down; resistance)
    Zone bounds: (bottom, top) in price.
    """

    index: int  # index of candle[i] (right candle of the 3)
    bullish: bool
    bottom: float
    top: float

    @property
    def mid(self) -> float:
        return 0.5 * (self.bottom + self.top)


@dataclass(frozen=True)
class OrderBlock:
    """Simplified OB: opposing candle before impulsive move that made BOS."""

    index: int
    bullish: bool  # bullish OB = demand (last down candle before up BOS)
    bottom: float
    top: float


def find_swing_points(
    highs: Sequence[float],
    lows: Sequence[float],
    left: int = 3,
    right: int = 3,
) -> List[SwingPoint]:
    """
    Fractal-style swings: a swing high at i if high[i] is strictly greater
    than highs in [i-left, i) and (i, i+right]. Same for lows (strictly less).

    Confirmed swings only (needs `right` bars after the pivot), so the last
    `right` bars never produce a new swing — by design (no look-ahead on
    unconfirmed pivots when evaluating at the series end).
    """
    if left < 1 or right < 1:
        raise ValueError("left/right must be >= 1")
    n = len(highs)
    if len(lows) != n:
        raise ValueError("highs and lows must be same length")
    out: List[SwingPoint] = []
    # i must have left bars before and right bars after
    for i in range(left, n - right):
        h = highs[i]
        is_sh = all(h > highs[i - k] for k in range(1, left + 1)) and all(
            h > highs[i + k] for k in range(1, right + 1)
        )
        l = lows[i]
        is_sl = all(l < lows[i - k] for k in range(1, left + 1)) and all(
            l < lows[i + k] for k in range(1, right + 1)
        )
        if is_sh:
            out.append(SwingPoint(index=i, price=h, kind="high"))
        if is_sl:
            out.append(SwingPoint(index=i, price=l, kind="low"))
    out.sort(key=lambda s: s.index)
    return out


def detect_bos_events(
    closes: Sequence[float],
    swings: Sequence[SwingPoint],
    swing_right: int = 3,
) -> List[StructureEvent]:
    """
    Walk forward: a close beyond the most recent *unbroken* swing high/low
    registers a BOS. After a bullish BOS, that swing high is considered broken;
    next bullish BOS needs a newer swing high, etc.

    A swing is only activated once bar index >= swing.index + swing_right
    (fractal confirmation), avoiding look-ahead within a full series.

    CHoCH is not labeled separately — the first counter-trend BOS is simply
    the opposite-side event (callers treat last event direction as structure).
    """
    events: List[StructureEvent] = []
    last_broken_high_idx = -1
    last_broken_low_idx = -1
    swing_list = list(swings)
    si = 0
    active_highs: List[SwingPoint] = []
    active_lows: List[SwingPoint] = []

    for i, close in enumerate(closes):
        while si < len(swing_list) and swing_list[si].index + swing_right <= i:
            sp = swing_list[si]
            if sp.kind == "high":
                active_highs.append(sp)
            else:
                active_lows.append(sp)
            si += 1

        # Most recent unbroken swing high / low
        sh = None
        for s in reversed(active_highs):
            if s.index > last_broken_high_idx and s.index < i:
                sh = s
                break
        sl = None
        for s in reversed(active_lows):
            if s.index > last_broken_low_idx and s.index < i:
                sl = s
                break

        bull = sh is not None and close > sh.price
        bear = sl is not None and close < sl.price
        # If both somehow (rare), prefer the closer swing in index (more recent)
        if bull and bear:
            assert sh is not None and sl is not None
            if sh.index >= sl.index:
                bear = False
            else:
                bull = False
        if bull and sh is not None:
            events.append(StructureEvent(index=i, broken_swing=sh, bullish=True))
            last_broken_high_idx = sh.index
        elif bear and sl is not None:
            events.append(StructureEvent(index=i, broken_swing=sl, bullish=False))
            last_broken_low_idx = sl.index
    return events


def structure_ok(
    closes: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    side_long: bool,
    swing_left: int = 3,
    swing_right: int = 3,
    max_age_bars: int = 40,
) -> Tuple[bool, str]:
    """
    Require the most recent BOS within `max_age_bars` to align with trade side.

    LONG -> last BOS bullish (broke a swing high).
    SHORT -> last BOS bearish (broke a swing low).
    """
    swings = find_swing_points(highs, lows, swing_left, swing_right)
    if len(swings) < 2:
        return False, "structure: fewer than 2 swing points"
    events = detect_bos_events(closes, swings, swing_right=swing_right)
    if not events:
        return False, "structure: no BOS detected"
    last = events[-1]
    age = len(closes) - 1 - last.index
    if age > max_age_bars:
        return (
            False,
            f"structure: last BOS {age} bars ago > max_age={max_age_bars}",
        )
    if side_long and not last.bullish:
        return (
            False,
            f"structure: last BOS bearish (broke L={last.broken_swing.price:.4f} "
            f"@{last.broken_swing.index}); need bullish for LONG",
        )
    if (not side_long) and last.bullish:
        return (
            False,
            f"structure: last BOS bullish (broke H={last.broken_swing.price:.4f} "
            f"@{last.broken_swing.index}); need bearish for SHORT",
        )
    kind = "bullish BOS" if last.bullish else "bearish BOS"
    return (
        True,
        f"structure: {kind} @bar {last.index} "
        f"(broke {last.broken_swing.kind[0].upper()}={last.broken_swing.price:.4f}, age={age})",
    )


def detect_fvgs(
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 60,
) -> List[FairValueGap]:
    """
    Detect 3-candle FVGs in the last `lookback` bars.

    Bullish: lows[i] > highs[i-2]  -> zone [highs[i-2], lows[i]]
    Bearish: highs[i] < lows[i-2]  -> zone [highs[i], lows[i-2]]
    """
    n = len(highs)
    if len(lows) != n or n < 3:
        return []
    start = max(2, n - lookback)
    out: List[FairValueGap] = []
    for i in range(start, n):
        if lows[i] > highs[i - 2]:
            out.append(
                FairValueGap(
                    index=i,
                    bullish=True,
                    bottom=highs[i - 2],
                    top=lows[i],
                )
            )
        elif highs[i] < lows[i - 2]:
            out.append(
                FairValueGap(
                    index=i,
                    bullish=False,
                    bottom=highs[i],
                    top=lows[i - 2],
                )
            )
    return out


def _fvg_filled(
    fvg: FairValueGap,
    highs: Sequence[float],
    lows: Sequence[float],
    from_index: int,
    to_index: int,
) -> bool:
    """Filled if any later bar fully trades through the zone."""
    for j in range(from_index, to_index + 1):
        if fvg.bullish:
            # Bullish gap filled when price trades down through bottom
            if lows[j] <= fvg.bottom:
                return True
        else:
            if highs[j] >= fvg.top:
                return True
    return False


def fvg_ok(
    price: float,
    highs: Sequence[float],
    lows: Sequence[float],
    side_long: bool,
    lookback: int = 60,
    atr_val: float = 0.0,
    touch_atr: float = 0.35,
) -> Tuple[bool, str]:
    """
    Require a recent *unfilled* FVG in trade direction that price is
    interacting with (inside zone or within touch_atr * ATR of the zone).

    LONG -> bullish FVG (demand imbalance) as support.
    SHORT -> bearish FVG (supply imbalance) as resistance.
    """
    fvgs = detect_fvgs(highs, lows, lookback=lookback)
    n = len(highs)
    if n == 0:
        return False, "fvg: no data"
    last_i = n - 1
    candidates = [f for f in fvgs if f.bullish == side_long]
    if not candidates:
        return False, "fvg: no directional FVG in lookback"

    tol = max(atr_val * touch_atr, price * 0.0005) if atr_val > 0 else price * 0.001
    best: Optional[FairValueGap] = None
    best_dist = float("inf")

    for fvg in reversed(candidates):
        # Only consider FVGs formed before the current bar
        if fvg.index >= last_i:
            continue
        if _fvg_filled(fvg, highs, lows, fvg.index + 1, last_i):
            continue
        # Distance from price to zone
        if fvg.bottom <= price <= fvg.top:
            dist = 0.0
        elif price < fvg.bottom:
            dist = fvg.bottom - price
        else:
            dist = price - fvg.top
        # Also accept if current bar wick touched the zone
        touched = lows[last_i] <= fvg.top and highs[last_i] >= fvg.bottom
        if dist <= tol or touched:
            if dist < best_dist:
                best_dist = dist
                best = fvg

    if best is None:
        return (
            False,
            f"fvg: no unfilled {'bullish' if side_long else 'bearish'} "
            f"FVG near price (tol={tol:.4f})",
        )
    kind = "bullish" if best.bullish else "bearish"
    return (
        True,
        f"fvg: near {kind} FVG [{best.bottom:.4f},{best.top:.4f}] "
        f"@bar {best.index} (dist={best_dist:.4f})",
    )


def find_order_block(
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    bos: StructureEvent,
    lookback: int = 15,
) -> Optional[OrderBlock]:
    """
    Simplified OB: last opposing candle before the impulsive move into BOS.

    Bullish BOS -> last bearish candle (close < open) in (bos.index-lookback, bos.index)
    Bearish BOS -> last bullish candle (close > open) in that window.
    Zone = candle body [min(o,c), max(o,c)].
    """
    start = max(0, bos.index - lookback)
    end = bos.index  # exclusive of BOS bar for the opposing candle search
    if end <= start:
        return None
    if bos.bullish:
        # last down candle
        for i in range(end - 1, start - 1, -1):
            if closes[i] < opens[i]:
                bottom = min(opens[i], closes[i])
                top = max(opens[i], closes[i])
                if top > bottom:
                    return OrderBlock(index=i, bullish=True, bottom=bottom, top=top)
    else:
        for i in range(end - 1, start - 1, -1):
            if closes[i] > opens[i]:
                bottom = min(opens[i], closes[i])
                top = max(opens[i], closes[i])
                if top > bottom:
                    return OrderBlock(index=i, bullish=False, bottom=bottom, top=top)
    return None


def order_block_ok(
    price: float,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    side_long: bool,
    atr_val: float,
    swing_left: int = 3,
    swing_right: int = 3,
    max_age_bars: int = 40,
    ob_lookback: int = 15,
    touch_atr: float = 0.5,
) -> Tuple[bool, str]:
    """
    Require price near the simplified order block of the latest aligned BOS.
    """
    swings = find_swing_points(highs, lows, swing_left, swing_right)
    events = detect_bos_events(closes, swings, swing_right=swing_right)
    if not events:
        return False, "ob: no BOS for order block"
    # Prefer latest BOS matching side
    aligned = [e for e in events if e.bullish == side_long]
    if not aligned:
        return False, "ob: no side-aligned BOS"
    bos = aligned[-1]
    age = len(closes) - 1 - bos.index
    if age > max_age_bars:
        return False, f"ob: aligned BOS too old ({age}>{max_age_bars})"
    ob = find_order_block(opens, highs, lows, closes, bos, lookback=ob_lookback)
    if ob is None:
        return False, "ob: no opposing candle before BOS"
    tol = max(atr_val * touch_atr, price * 0.0005) if atr_val > 0 else price * 0.001
    if ob.bottom - tol <= price <= ob.top + tol:
        kind = "bullish/demand" if ob.bullish else "bearish/supply"
        return (
            True,
            f"ob: near {kind} OB [{ob.bottom:.4f},{ob.top:.4f}] "
            f"@bar {ob.index} (tol={tol:.4f})",
        )
    # Wick touch on current bar
    last = len(closes) - 1
    if lows[last] <= ob.top + tol and highs[last] >= ob.bottom - tol:
        kind = "bullish/demand" if ob.bullish else "bearish/supply"
        return (
            True,
            f"ob: wick touch {kind} OB [{ob.bottom:.4f},{ob.top:.4f}] @bar {ob.index}",
        )
    return (
        False,
        f"ob: price {price:.4f} not near OB [{ob.bottom:.4f},{ob.top:.4f}] "
        f"(tol={tol:.4f})",
    )


def smc_confluence(
    price: float,
    opens: Sequence[float],
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    side_long: bool,
    atr_val: float,
    *,
    require_structure: bool = True,
    require_fvg: bool = True,
    require_ob: bool = False,
    swing_left: int = 3,
    swing_right: int = 3,
    structure_max_age: int = 40,
    fvg_lookback: int = 60,
    fvg_touch_atr: float = 0.35,
    ob_lookback: int = 15,
    ob_touch_atr: float = 0.5,
    ob_max_age: int = 40,
) -> Tuple[bool, str]:
    """
    Run enabled SMC pieces; return (ok, detail). On failure, detail starts
    with structure:/fvg:/ob: for clear engine skip logging.
    """
    parts: List[str] = []
    if require_structure:
        ok, detail = structure_ok(
            closes,
            highs,
            lows,
            side_long,
            swing_left=swing_left,
            swing_right=swing_right,
            max_age_bars=structure_max_age,
        )
        if not ok:
            return False, detail
        parts.append(detail)
    if require_fvg:
        ok, detail = fvg_ok(
            price,
            highs,
            lows,
            side_long,
            lookback=fvg_lookback,
            atr_val=atr_val,
            touch_atr=fvg_touch_atr,
        )
        if not ok:
            return False, detail
        parts.append(detail)
    if require_ob:
        ok, detail = order_block_ok(
            price,
            opens,
            highs,
            lows,
            closes,
            side_long,
            atr_val,
            swing_left=swing_left,
            swing_right=swing_right,
            max_age_bars=ob_max_age,
            ob_lookback=ob_lookback,
            touch_atr=ob_touch_atr,
        )
        if not ok:
            return False, detail
        parts.append(detail)
    return True, "; ".join(parts) if parts else "smc: no pieces enabled"
