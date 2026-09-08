"""Signal engine: direction from EMA+RSI, levels, cooldown, skip logging."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

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

    def decide_direction(
        self, closes: list
    ) -> Tuple[Optional[Side], str, float, float, float]:
        """
        LONG: fast EMA > slow EMA and RSI < overbought.
        SHORT: fast EMA < slow EMA and RSI > oversold.
        Otherwise skip (mixed/choppy).
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

        if bullish and rsi_val < cfg.rsi_overbought:
            return (
                Side.LONG,
                f"EMA{cfg.ema_fast}>EMA{cfg.ema_slow} (bullish) and RSI={rsi_val:.1f}<{cfg.rsi_overbought}",
                fast,
                slow,
                rsi_val,
            )
        if bearish and rsi_val > cfg.rsi_oversold:
            return (
                Side.SHORT,
                f"EMA{cfg.ema_fast}<EMA{cfg.ema_slow} (bearish) and RSI={rsi_val:.1f}>{cfg.rsi_oversold}",
                fast,
                slow,
                rsi_val,
            )

        # Mixed / choppy / filtered
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

    def evaluate_symbol(self, symbol: str) -> Optional[Signal]:
        """Fetch klines, decide direction, build signal or return None."""
        cfg = self.config
        candles = self.client.get_klines(symbol, cfg.interval, cfg.kline_limit)
        closes = [c["close"] for c in candles]
        if not closes:
            logger.warning("%s: no kline data", symbol)
            return None

        side, reason, fast, slow, rsi_val = self.decide_direction(closes)
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
