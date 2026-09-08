"""Confluence gates for SignalEngine (Fib/MACD/ATR/HTF/ST/volume/SMC)."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .config import Config
from .htf_supertrend import htf_ema_bias, supertrend_agrees
from .indicators import adx, atr, fib_confluence, last_valid, macd
from .models import Side
from .smc import smc_confluence
from .volume import volume_price_agreement, volume_ratio_ok


def apply_confluence(
    cfg: Config,
    side: Side,
    closes: Sequence[float],
    highs: Optional[Sequence[float]],
    lows: Optional[Sequence[float]],
    base_reason: str,
    volumes: Optional[Sequence[float]] = None,
    opens: Optional[Sequence[float]] = None,
    htf_closes: Optional[Sequence[float]] = None,
) -> Tuple[Optional[Side], str]:
    """Apply Fib/MACD/ATR/ADX/HTF/Supertrend/volume/SMC gates.

    Returns (side|None, reason). On failure, reason starts with 'skip ...'.
    """
    price = closes[-1]
    parts: List[str] = [base_reason]

    atr_val: Optional[float] = None
    need_atr = (
        cfg.filter_atr or cfg.filter_fib or cfg.filter_smc or cfg.filter_supertrend
    )
    if need_atr:
        if highs is None or lows is None:
            return None, "skip: OHLC required for ATR/Fib/SMC filters but missing"
        atr_series = atr(highs, lows, closes, cfg.atr_period)
        atr_val = last_valid(atr_series)
        if atr_val is None or atr_val <= 0:
            return None, "skip: insufficient ATR data"

    if cfg.filter_atr:
        assert atr_val is not None
        atr_pct = (atr_val / price) * 100.0 if price else 0.0
        if atr_pct < cfg.atr_min_pct:
            return None, f"skip: ATR% too low (chop) ATR%={atr_pct:.3f}<{cfg.atr_min_pct}"
        if cfg.atr_max_pct > 0 and atr_pct > cfg.atr_max_pct:
            return None, f"skip: ATR% too high (extreme) ATR%={atr_pct:.3f}>{cfg.atr_max_pct}"
        parts.append(f"ATR%={atr_pct:.3f}")

    if cfg.filter_macd:
        macd_series = macd(closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal)
        point = last_valid(macd_series)
        if point is None:
            return None, "skip: insufficient MACD data"
        bullish_macd = point.macd > point.signal
        if side == Side.LONG and not bullish_macd:
            return None, (
                f"skip LONG: MACD disagrees "
                f"(macd={point.macd:.6f} signal={point.signal:.6f} hist={point.histogram:.6f})"
            )
        if side == Side.SHORT and bullish_macd:
            return None, (
                f"skip SHORT: MACD disagrees "
                f"(macd={point.macd:.6f} signal={point.signal:.6f} hist={point.histogram:.6f})"
            )
        parts.append(
            f"MACD hist={point.histogram:.6f} ({'bull' if bullish_macd else 'bear'})"
        )

    if cfg.filter_fib:
        assert highs is not None and lows is not None
        assert atr_val is not None
        tol_pct = price * (cfg.fib_tol_pct / 100.0)
        tol_atr = atr_val * cfg.fib_tol_atr
        tolerance = max(tol_pct, tol_atr)
        ok, detail = fib_confluence(
            price=price,
            side_long=(side == Side.LONG),
            highs=highs,
            lows=lows,
            lookback=cfg.fib_lookback,
            tolerance=tolerance,
            ratios=cfg.fib_levels,
        )
        if not ok:
            return None, f"skip {side.value}: Fib - {detail}"
        parts.append(f"Fib OK ({detail})")

    if cfg.filter_adx:
        if highs is None or lows is None:
            return None, "skip: OHLC required for ADX but missing"
        adx_series = adx(highs, lows, closes, cfg.adx_period)
        adx_val = last_valid(adx_series)
        if adx_val is None:
            return None, "skip: insufficient ADX data"
        if adx_val < cfg.adx_min:
            return None, f"skip: ADX too weak ({adx_val:.1f}<{cfg.adx_min})"
        parts.append(f"ADX={adx_val:.1f}")

    if cfg.filter_htf:
        if htf_closes is None:
            return None, "skip: HTF closes required for FILTER_HTF but missing"
        ok, detail = htf_ema_bias(
            htf_closes,
            side_long=(side == Side.LONG),
            fast=cfg.htf_ema_fast,
            slow=cfg.htf_ema_slow,
        )
        if not ok:
            return None, f"skip {side.value}: {detail}"
        parts.append(detail)

    if cfg.filter_supertrend:
        if highs is None or lows is None:
            return None, "skip: OHLC required for Supertrend but missing"
        ok, detail = supertrend_agrees(
            highs,
            lows,
            closes,
            side_long=(side == Side.LONG),
            period=cfg.supertrend_period,
            multiplier=cfg.supertrend_multiplier,
        )
        if not ok:
            return None, f"skip {side.value}: {detail}"
        parts.append(detail)

    if cfg.filter_volume:
        if volumes is None:
            return None, "skip: volume required for FILTER_VOLUME but missing"
        ok, detail = volume_ratio_ok(
            volumes,
            period=cfg.vol_sma_period,
            min_ratio=cfg.vol_ratio_min,
            confirm_bars=cfg.vol_confirm_bars,
        )
        if not ok:
            return None, f"skip {side.value}: {detail}"
        parts.append(detail)

    if cfg.filter_obv:
        if volumes is None:
            return None, "skip: volume required for FILTER_OBV but missing"
        ok, detail = volume_price_agreement(
            closes,
            volumes,
            side_long=(side == Side.LONG),
            obv_lookback=cfg.obv_lookback,
        )
        if not ok:
            return None, f"skip {side.value}: {detail}"
        parts.append(detail)

    if cfg.filter_smc:
        if highs is None or lows is None:
            return None, "skip: OHLC required for SMC but missing"
        if opens is None:
            opens = [closes[0]] + list(closes[:-1])
        assert atr_val is not None
        ok, detail = smc_confluence(
            price=price,
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            side_long=(side == Side.LONG),
            atr_val=atr_val,
            require_structure=cfg.filter_smc_structure,
            require_fvg=cfg.filter_smc_fvg,
            require_ob=cfg.filter_smc_ob,
            swing_left=cfg.smc_swing_left,
            swing_right=cfg.smc_swing_right,
            structure_max_age=cfg.smc_structure_max_age,
            fvg_lookback=cfg.smc_fvg_lookback,
            fvg_touch_atr=cfg.smc_fvg_touch_atr,
            ob_lookback=cfg.smc_ob_lookback,
            ob_touch_atr=cfg.smc_ob_touch_atr,
            ob_max_age=cfg.smc_ob_max_age,
        )
        if not ok:
            return None, f"skip {side.value}: {detail}"
        parts.append(detail)

    return side, "; ".join(parts)
