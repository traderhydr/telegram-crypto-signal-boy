"""Signal engine: EMA+RSI direction with Fib/MACD/ATR/ADX + volume/SMC confluence."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .binance_client import BinanceFuturesClient
from .config import Config
from .indicators import (
    adx,
    atr,
    ema,
    fib_confluence,
    last_valid,
    macd,
    rsi,
)
from .levels import generate_levels
from .models import Side, Signal
from .smc import smc_confluence
from .volume import volume_price_agreement, volume_ratio_ok

logger = logging.getLogger(__name__)


class SignalEngine:
    def __init__(self, config: Config, client: Optional[BinanceFuturesClient] = None):
        self.config = config
        self.client = client or BinanceFuturesClient(config.binance_futures_base)
        # key: (symbol, side) -> last signal UTC time
        self._last_signal_at: Dict[Tuple[str, Side], datetime] = {}

    def _cooldown_active(self, symbol: str, side: Side) -> bool:
        key = (symbol, side)
        last = self._last_signal_at.get(key)
        if last is None:
            return False
        elapsed = datetime.now(timezone.utc) - last
        return elapsed < timedelta(hours=self.config.cooldown_hours)

    def _mark_sent(self, symbol: str, side: Side) -> None:
        self._last_signal_at[(symbol, side)] = datetime.now(timezone.utc)

    def _needs_ohlc(self) -> bool:
        cfg = self.config
        return (
            cfg.filter_fib
            or cfg.filter_atr
            or cfg.filter_adx
            or cfg.filter_smc
        )

    def _any_confluence(self) -> bool:
        cfg = self.config
        return (
            cfg.filter_fib
            or cfg.filter_macd
            or cfg.filter_atr
            or cfg.filter_adx
            or cfg.filter_volume
            or cfg.filter_obv
            or cfg.filter_smc
        )

    def _apply_confluence(
        self,
        side: Side,
        closes: Sequence[float],
        highs: Optional[Sequence[float]],
        lows: Optional[Sequence[float]],
        base_reason: str,
        volumes: Optional[Sequence[float]] = None,
        opens: Optional[Sequence[float]] = None,
    ) -> Tuple[Optional[Side], str]:
        """
        Apply Fib / MACD / ATR / ADX / volume / SMC gates.
        Returns (side|None, reason). On failure, reason starts with 'skip ...'.
        """
        cfg = self.config
        price = closes[-1]
        parts: List[str] = [base_reason]

        # --- ATR volatility filter ---
        atr_val: Optional[float] = None
        need_atr = (
            cfg.filter_atr
            or cfg.filter_fib
            or cfg.filter_smc
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
                return (
                    None,
                    f"skip: ATR% too low (chop) ATR%={atr_pct:.3f}<{cfg.atr_min_pct}",
                )
            if cfg.atr_max_pct > 0 and atr_pct > cfg.atr_max_pct:
                return (
                    None,
                    f"skip: ATR% too high (extreme) ATR%={atr_pct:.3f}>{cfg.atr_max_pct}",
                )
            parts.append(f"ATR%={atr_pct:.3f}")

        # --- MACD confirmation (must agree with EMA direction) ---
        if cfg.filter_macd:
            macd_series = macd(
                closes, cfg.macd_fast, cfg.macd_slow, cfg.macd_signal
            )
            point = last_valid(macd_series)
            if point is None:
                return None, "skip: insufficient MACD data"
            bullish_macd = point.macd > point.signal  # equiv. histogram > 0
            if side == Side.LONG and not bullish_macd:
                return (
                    None,
                    f"skip LONG: MACD disagrees "
                    f"(macd={point.macd:.6f} signal={point.signal:.6f} hist={point.histogram:.6f})",
                )
            if side == Side.SHORT and bullish_macd:
                return (
                    None,
                    f"skip SHORT: MACD disagrees "
                    f"(macd={point.macd:.6f} signal={point.signal:.6f} hist={point.histogram:.6f})",
                )
            parts.append(
                f"MACD hist={point.histogram:.6f} ({'bull' if bullish_macd else 'bear'})"
            )

        # --- Fibonacci confluence ---
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

        # --- ADX trend-strength gate ---
        if cfg.filter_adx:
            if highs is None or lows is None:
                return None, "skip: OHLC required for ADX but missing"
            adx_series = adx(highs, lows, closes, cfg.adx_period)
            adx_val = last_valid(adx_series)
            if adx_val is None:
                return None, "skip: insufficient ADX data"
            if adx_val < cfg.adx_min:
                return (
                    None,
                    f"skip: ADX too weak ({adx_val:.1f}<{cfg.adx_min})",
                )
            parts.append(f"ADX={adx_val:.1f}")

        # --- Volume: relative volume ---
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

        # --- Volume: OBV / volume-price agreement ---
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

        # --- SMC (structure + FVG; optional OB) ---
        if cfg.filter_smc:
            if highs is None or lows is None:
                return None, "skip: OHLC required for SMC but missing"
            if opens is None:
                # Fallback: approximate opens with prior close (engine always
                # prefers real opens when available).
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
                # detail already starts with structure:/fvg:/ob:
                return None, f"skip {side.value}: {detail}"
            parts.append(detail)

        return side, "; ".join(parts)

    def decide_direction(
        self,
        closes: list,
        highs: Optional[list] = None,
        lows: Optional[list] = None,
        volumes: Optional[list] = None,
        opens: Optional[list] = None,
    ) -> Tuple[Optional[Side], str, float, float, float]:
        """
        Base: LONG if fast EMA > slow EMA and RSI < overbought;
              SHORT if fast EMA < slow EMA and RSI > oversold.

        Confluence (when enabled via Config):
          Fib / MACD / ATR / ADX / relative volume / OBV / SMC (BOS+FVG[+OB]).

        Pass highs/lows/volumes/opens (same length as closes) when filters need them.
        Returns (side|None, reason, fast_ema, slow_ema, rsi).
        """
        cfg = self.config
        fast_series = ema(closes, cfg.ema_fast)
        slow_series = ema(closes, cfg.ema_slow)
        rsi_series = rsi(closes, cfg.rsi_period)

        fast = last_valid(fast_series)
        slow = last_valid(slow_series)
        rsi_val = last_valid(rsi_series)

        if fast is None or slow is None or rsi_val is None:
            return None, "insufficient indicator data", 0.0, 0.0, 0.0

        bullish = fast > slow
        bearish = fast < slow

        candidate: Optional[Side] = None
        base_reason = ""

        if bullish and rsi_val < cfg.rsi_overbought:
            candidate = Side.LONG
            base_reason = (
                f"EMA{cfg.ema_fast}>EMA{cfg.ema_slow} (bullish) and "
                f"RSI={rsi_val:.1f}<{cfg.rsi_overbought}"
            )
        elif bearish and rsi_val > cfg.rsi_oversold:
            candidate = Side.SHORT
            base_reason = (
                f"EMA{cfg.ema_fast}<EMA{cfg.ema_slow} (bearish) and "
                f"RSI={rsi_val:.1f}>{cfg.rsi_oversold}"
            )
        else:
            # Mixed / choppy / RSI filtered
            if bullish and rsi_val >= cfg.rsi_overbought:
                reason = (
                    f"skip LONG: bullish EMA but RSI overbought "
                    f"({rsi_val:.1f}>={cfg.rsi_overbought})"
                )
            elif bearish and rsi_val <= cfg.rsi_oversold:
                reason = (
                    f"skip SHORT: bearish EMA but RSI oversold "
                    f"({rsi_val:.1f}<={cfg.rsi_oversold})"
                )
            elif abs(fast - slow) < 1e-12:
                reason = "skip: EMAs equal (flat)"
            else:
                reason = (
                    f"skip: mixed/choppy "
                    f"(fast={fast:.4f} slow={slow:.4f} rsi={rsi_val:.1f})"
                )
            return None, reason, fast, slow, rsi_val

        if self._any_confluence():
            side, reason = self._apply_confluence(
                candidate,
                closes,
                highs,
                lows,
                base_reason,
                volumes=volumes,
                opens=opens,
            )
            return side, reason, fast, slow, rsi_val

        return candidate, base_reason, fast, slow, rsi_val

    def evaluate_symbol(self, symbol: str) -> Optional[Signal]:
        """Fetch klines, decide direction, build signal or return None."""
        cfg = self.config
        candles = self.client.get_klines(symbol, cfg.interval, cfg.kline_limit)
        opens = [c["open"] for c in candles]
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        volumes = [c["volume"] for c in candles]
        if not closes:
            logger.warning("%s: no kline data", symbol)
            return None

        side, reason, fast, slow, rsi_val = self.decide_direction(
            closes, highs=highs, lows=lows, volumes=volumes, opens=opens
        )
        if side is None:
            logger.info("%s: %s", symbol, reason)
            return None

        if self._cooldown_active(symbol, side):
            logger.info(
                "%s %s: cooldown active (%.1fh)",
                symbol,
                side.value,
                cfg.cooldown_hours,
            )
            return None

        ref = closes[-1]
        entries, tps, sl = generate_levels(
            ref,
            side,
            cfg.entry_offsets_pct,
            cfg.tp_targets_pct,
            cfg.sl_beyond_ladder_pct,
        )

        signal = Signal(
            symbol=symbol,
            side=side,
            leverage=cfg.leverage,
            entries=entries,
            take_profits=tps,
            stop_loss=sl,
            rationale=reason,
            reference_price=ref,
            fast_ema=fast,
            slow_ema=slow,
            rsi=rsi_val,
        )
        self._mark_sent(symbol, side)
        return signal

    def scan(self) -> list:
        """Evaluate all configured symbols; return list of new signals."""
        signals = []
        for symbol in self.config.symbols:
            try:
                sig = self.evaluate_symbol(symbol)
                if sig:
                    signals.append(sig)
            except Exception:
                logger.exception("Error evaluating %s", symbol)
        return signals
