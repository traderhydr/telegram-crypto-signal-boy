"""Signal engine: EMA+RSI direction with Fib/MACD/ATR/HTF/Supertrend (+ optional volume/SMC)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from .binance_client import BinanceFuturesClient
from .config import Config
from .indicators import ema, last_valid, rsi
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
        return (
            cfg.filter_fib
            or cfg.filter_atr
            or cfg.filter_adx
            or cfg.filter_smc
            or cfg.filter_supertrend
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
            or cfg.filter_htf
            or cfg.filter_supertrend
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
        htf_closes: Optional[Sequence[float]] = None,
    ) -> Tuple[Optional[Side], str]:
        from .engine_confluence import apply_confluence
        return apply_confluence(
            self.config, side, closes, highs, lows, base_reason,
            volumes=volumes, opens=opens, htf_closes=htf_closes,
        )

    def decide_direction(
        self,
        closes: list,
        highs: Optional[list] = None,
        lows: Optional[list] = None,
        volumes: Optional[list] = None,
        opens: Optional[list] = None,
        htf_closes: Optional[list] = None,
    ) -> Tuple[Optional[Side], str, float, float, float]:
        """EMA+RSI base direction; optional confluence via Config. Returns (side, reason, emas, rsi)."""
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
                htf_closes=htf_closes,
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

        htf_closes = None
        if cfg.filter_htf:
            htf_candles = self.client.get_klines(
                symbol, cfg.htf_interval, cfg.htf_kline_limit
            )
            # Drop the still-forming HTF candle to avoid lookahead.
            now_ms = int(time.time() * 1000)
            htf_closes = [
                c["close"] for c in htf_candles if c["close_time"] <= now_ms
            ]

        side, reason, fast, slow, rsi_val = self.decide_direction(
            closes,
            highs=highs,
            lows=lows,
            volumes=volumes,
            opens=opens,
            htf_closes=htf_closes,
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
