"""EMA+RSI (+ Fib/MACD/ATR/HTF/Supertrend; optional volume/SMC) strategy backtester.

See README Backtest section for fill/path assumptions (Entry1 touch, 20% TPs,
conservative OHLC, cooldown, R-multiples).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional, Sequence

from .backtest_core import (
    SymbolMetrics,
    TradeResult,
    _ms_to_dt,
    bar_touches_entry,
    r_for_exit,
    risk_unit,
    simulate_open_trade,
    update_metrics,
)
from .htf_supertrend import completed_htf_closes, resample_klines_to_htf
from .intervals import INTERVAL_MS
from .config import Config
from .engine import SignalEngine
from .levels import generate_levels
from .models import Side

logger = logging.getLogger(__name__)

# Re-export helpers for tests: `from signal_bot.backtest import ...`



def backtest_symbol(
    candles: Sequence[dict],
    symbol: str,
    config: Config,
    engine: Optional[SignalEngine] = None,
) -> SymbolMetrics:
    """Walk candles chronologically and simulate the live strategy."""
    engine = engine or SignalEngine(config, client=None)
    metrics = SymbolMetrics(symbol=symbol)
    warm = config.warmup_bars()
    cooldown = timedelta(hours=config.cooldown_hours)
    last_signal_at: dict = {Side.LONG: None, Side.SHORT: None}
    open_until_index = -1
    opens = [c["open"] for c in candles]
    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c.get("volume", 0.0) for c in candles]

    htf_all = None
    if config.filter_htf:
        htf_ms = INTERVAL_MS.get(config.htf_interval)
        if htf_ms is None:
            raise ValueError(f"Unsupported HTF_INTERVAL: {config.htf_interval}")
        htf_all = resample_klines_to_htf(candles, htf_ms)

    for i in range(warm, len(candles)):
        if i <= open_until_index:
            continue

        htf_closes = None
        if htf_all is not None:
            htf_closes = completed_htf_closes(htf_all, candles[i]["close_time"])

        side, reason, fast, slow, rsi_val = engine.decide_direction(
            closes[: i + 1],
            highs=highs[: i + 1],
            lows=lows[: i + 1],
            volumes=volumes[: i + 1],
            opens=opens[: i + 1],
            htf_closes=htf_closes,
        )
        if side is None:
            continue

        bar_time = _ms_to_dt(candles[i]["close_time"])
        last = last_signal_at[side]
        if last is not None and (bar_time - last) < cooldown:
            continue

        ref = closes[i]
        entries, tps, sl = generate_levels(
            ref,
            side,
            config.entry_offsets_pct,
            config.tp_targets_pct,
            config.sl_beyond_ladder_pct,
        )
        entry1 = entries[0]
        last_signal_at[side] = bar_time

        trade = simulate_open_trade(candles, side, entry1, tps, sl, i)
        trade.symbol = symbol
        if not trade.filled:
            logger.debug("%s %s signal @ %s - entry not filled", symbol, side.value, bar_time)
            continue

        if trade.exit_time is not None:
            for k in range(i + 1, len(candles)):
                if _ms_to_dt(candles[k]["close_time"]) >= trade.exit_time:
                    open_until_index = k
                    break
            else:
                open_until_index = len(candles) - 1

        update_metrics(metrics, trade)
        logger.debug(
            "%s %s R=%.3f tps=%d stopped=%s reason=%s",
            symbol, side.value, trade.r_multiple, trade.tps_hit, trade.stopped, reason,
        )

    return metrics



from .backtest_run import (  # noqa: E402
    _filter_summary,
    format_report,
    merge_metrics,
    run_backtest,
)
from .backtest_cli import main  # noqa: E402
