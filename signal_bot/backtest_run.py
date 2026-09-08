"""Backtest report/CLI helpers (split for push size)."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from .backtest_core import SymbolMetrics, TradeResult, _ms_to_dt, update_metrics
from .binance_client import BinanceFuturesClient
from .config import Config
from .engine import SignalEngine
from .intervals import INTERVAL_MS

logger = logging.getLogger(__name__)

def merge_metrics(parts: Sequence[SymbolMetrics], label: str = "COMBINED") -> SymbolMetrics:
    combined = SymbolMetrics(symbol=label)
    all_trades: List[TradeResult] = []
    for p in parts:
        all_trades.extend(p.trade_results)
    all_trades.sort(key=lambda t: t.signal_time)
    for t in all_trades:
        update_metrics(combined, t)
    return combined

def _filter_summary(config: Config) -> str:
    flags = []
    if config.filter_fib:
        lv = "/".join(f"{x:g}" for x in config.fib_levels)
        flags.append(f"Fib(lb={config.fib_lookback},{lv})")
    if config.filter_macd:
        flags.append(
            f"MACD({config.macd_fast}/{config.macd_slow}/{config.macd_signal})"
        )
    if config.filter_atr:
        flags.append(f"ATR%>={config.atr_min_pct}")
    if config.filter_adx:
        flags.append(f"ADX>={config.adx_min}")
    if config.filter_volume:
        flags.append(
            f"Vol(SMA{config.vol_sma_period}>={config.vol_ratio_min})"
        )
    if config.filter_obv:
        flags.append(f"OBV(lb={config.obv_lookback})")
    if config.filter_smc:
        bits = []
        if config.filter_smc_structure:
            bits.append("BOS")
        if config.filter_smc_fvg:
            bits.append("FVG")
        if config.filter_smc_ob:
            bits.append("OB")
        flags.append("SMC(" + "+".join(bits or ["off"]) + ")")
    if config.filter_htf:
        flags.append(
            f"HTF({config.htf_interval} EMA{config.htf_ema_fast}/{config.htf_ema_slow})"
        )
    if config.filter_supertrend:
        flags.append(
            f"ST({config.supertrend_period}x{config.supertrend_multiplier:g})"
        )
    return "+".join(flags) if flags else "no confluence filters"

def format_report(
    per_symbol: Sequence[SymbolMetrics],
    combined: SymbolMetrics,
    start: datetime,
    end: datetime,
    days: float,
    config: Optional[Config] = None,
    interval: Optional[str] = None,
) -> str:
    filters = _filter_summary(config) if config else "Fib+MACD+ATR"
    tf = interval or (config.interval if config else "15m")
    lines = [
        "=" * 72,
        f"BACKTEST REPORT - EMA9/21 + RSI14 + [{filters}] @ {tf}",
        f"Date range: {start.strftime('%Y-%m-%d %H:%M UTC')} -> "
        f"{end.strftime('%Y-%m-%d %H:%M UTC')} (~{days:.0f} days)",
        "=" * 72,
        "",
        f"{'Symbol':<12} {'Trades':>7} {'Wins':>6} {'Losses':>7} "
        f"{'Win%':>7} {'Total R':>9} {'Avg R':>8} {'MaxDD R':>9} {'PF':>7}",
        "-" * 72,
    ]

    def row(m: SymbolMetrics) -> str:
        pf = m.profit_factor
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        return (
            f"{m.symbol:<12} {m.trades:>7} {m.wins:>6} {m.losses:>7} "
            f"{m.win_rate:>6.1f}% {m.total_r:>9.2f} {m.avg_r:>8.3f} "
            f"{m.max_drawdown_r:>9.2f} {pf_s:>7}"
        )

    for m in per_symbol:
        lines.append(row(m))
    lines.append("-" * 72)
    lines.append(row(combined))
    lines.append("=" * 72)
    lines.append("")
    lines.append("Assumptions: Entry1 touch fill; 20% size per TP; conservative")
    lines.append("OHLC (adverse before favorable); cooldown per symbol/side;")
    lines.append("one open position per symbol; metrics in R-multiples.")
    return "\n".join(lines)

def run_backtest(
    days: float = 120.0,
    symbols: Optional[Sequence[str]] = None,
    config: Optional[Config] = None,
    client: Optional[BinanceFuturesClient] = None,
) -> Tuple[List[SymbolMetrics], SymbolMetrics, str]:
    config = config or Config.from_env()
    symbols = list(symbols) if symbols else list(config.symbols)
    client = client or BinanceFuturesClient(config.binance_futures_base)
    from .backtest import backtest_symbol
    engine = SignalEngine(config, client=None)

    interval = config.interval
    interval_ms = INTERVAL_MS.get(interval, 900_000)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - int(days * 24 * 60 * 60 * 1000)
    warm = config.warmup_bars() + 5
    # Extra LTF bars so resampled HTF EMA(slow) is ready at the evaluation start.
    if config.filter_htf:
        htf_ms = INTERVAL_MS.get(config.htf_interval, 14_400_000)
        bars_per_htf = max(1, htf_ms // interval_ms)
        warm += config.htf_ema_slow * bars_per_htf + bars_per_htf
    fetch_start = start_ms - warm * interval_ms

    per_symbol: List[SymbolMetrics] = []
    range_start: Optional[datetime] = None
    range_end: Optional[datetime] = None

    skipped: List[str] = []
    for symbol in symbols:
        logger.info("Fetching ~%.0f days of %s %s klines...", days, symbol, interval)
        try:
            candles = client.get_historical_klines(
                symbol, interval=interval, start_time=fetch_start, end_time=end_ms,
            )
            if len(candles) < warm + 10:
                raise RuntimeError(
                    f"Not enough candles for {symbol}: got {len(candles)}, need >{warm}"
                )
            eval_candles = [
                c for c in candles if c["open_time"] >= start_ms - warm * interval_ms
            ]
            logger.info("%s: %d candles loaded", symbol, len(eval_candles))
            m = backtest_symbol(eval_candles, symbol, config, engine)
            per_symbol.append(m)
            if eval_candles:
                cs = _ms_to_dt(eval_candles[0]["open_time"])
                ce = _ms_to_dt(eval_candles[-1]["close_time"])
                range_start = cs if range_start is None else min(range_start, cs)
                range_end = ce if range_end is None else max(range_end, ce)
        except Exception as exc:
            logger.error(
                "Skipping %s: failed to fetch/backtest (%s). Continuing with other symbols.",
                symbol,
                exc,
            )
            skipped.append(symbol)

    if not per_symbol:
        raise RuntimeError(
            "No symbols produced backtest results"
            + (f"; skipped: {', '.join(skipped)}" if skipped else "")
        )
    if skipped:
        logger.warning("Skipped symbols due to fetch/data errors: %s", ", ".join(skipped))

    combined = merge_metrics(per_symbol)
    assert range_start and range_end
    report = format_report(
        per_symbol, combined, range_start, range_end, days,
        config=config, interval=interval,
    )
    return per_symbol, combined, report
