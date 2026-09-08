"""Signal engine: EMA+RSI direction with Fib/MACD/ATR/ADX confluence."""

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
        return cfg.filter_fib or cfg.filter_atr or cfg.filter_adx

    def _apply_confluence(
        self,
        side: Side,
        closes: Sequence[float],
        highs: Optional[Sequence[float]],
        lows: Optional[Sequence[float]],
        base_reason: str,
    ) -> Tuple[Optional[Side], str]:
        """
        Apply Fib / MACD / ATR / ADX gates. Returns (side|None, reason).
        On failure, reason starts with 'skip ...'.
        """
        cfg = self.config
        price = closes[-1]
        parts: List[str] = [base_reason]

        # --- ATR volatility filter ---
        atr_val: Optional[float] = None
        if cfg.filter_atr or cfg.filter_fib:
            if highs is None or lows is None:
                return None, "skip: OHLC required for ATR/Fib filters but missing"
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

        return side, "; ".join(parts)

    def decide_direction(
        self,
        closes: list,
        highs: Optional[list] = None,
        lows: Optional[list] = None,
    ) -> Tuple[Optional[Side], str, float, float, float]:
        """
        Base: LONG if fast EMA > slow EMA and RSI < overbought;
              SHORT if fast EMA < slow EMA and RSI > oversold.

        Confluence (when enabled via Config):
          1. Fib - price near configured Fib levels (default 0.5/0.618) of swing
          2. MACD - line > signal for LONG, opposite for SHORT
          3. ATR - ATR% of price within [min, max] (chop / optional extreme)
          4. ADX - ADX(14) >= adx_min (default 25)

        Pass highs/lows (same length as closes) when Fib/ATR/ADX filters are on.
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

        # Confluence filters
        if (
            cfg.filter_fib
            or cfg.filter_macd
            or cfg.filter_atr
            or cfg.filter_adx
        ):
            side, reason = self._apply_confluence(
                candidate, closes, highs, lows, base_reason
            )
            return side, reason, fast, slow, rsi_val

        return candidate, base_reason, fast, slow, rsi_val

    def evaluate_symbol(self, symbol: str) -> Optional[Signal]:
        """Fetch klines, decide direction, build signal or return None."""
        cfg = self.config
        candles = self.client.get_klines(symbol, cfg.interval, cfg.kline_limit)
        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        if not closes:
            logger.warning("%s: no kline data", symbol)
            return None

        side, reason, fast, slow, rsi_val = self.decide_direction(
            closes, highs=highs, lows=lows
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
