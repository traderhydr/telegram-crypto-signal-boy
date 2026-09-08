"""EMA+RSI (+ Fib/MACD/ATR/volume/SMC confluence) strategy backtester.

See README Backtest section for fill/path assumptions (Entry1 touch, 20% TPs,
conservative OHLC, cooldown, R-multiples).
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

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
from .binance_client import BinanceFuturesClient
from .config import Config
from .engine import SignalEngine
from .levels import generate_levels
from .models import Side

logger = logging.getLogger(__name__)

# Re-export helpers for tests: `from signal_bot.backtest import ...`
__all__ = [
    "TradeResult",
    "SymbolMetrics",
    "risk_unit",
    "r_for_exit",
    "bar_touches_entry",
    "simulate_open_trade",
    "run_backtest",
    "main",
]

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


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

    for i in range(warm, len(candles)):
        if i <= open_until_index:
            continue

        side, reason, fast, slow, rsi_val = engine.decide_direction(
            closes[: i + 1],
            highs=highs[: i + 1],
            lows=lows[: i + 1],
            volumes=volumes[: i + 1],
            opens=opens[: i + 1],
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
    engine = SignalEngine(config, client=None)

    interval = config.interval
    interval_ms = INTERVAL_MS.get(interval, 900_000)
    end_ms = int(time.time() * 1000)
    start_ms = end_ms - int(days * 24 * 60 * 60 * 1000)
    warm = config.warmup_bars() + 5
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


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backtest EMA+RSI+confluence signal strategy on Binance USDT-M history"
    )
    parser.add_argument("--days", type=float, default=120.0, help="Lookback days")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated symbols")
    parser.add_argument(
        "--interval",
        type=str,
        default="",
        help="Candle interval override (e.g. 15m, 1h). Default: INTERVAL env / Config",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = Config.from_env()
    if args.interval.strip():
        config.interval = args.interval.strip()
    ok, msg = config.validate()
    if not ok:
        logger.error("Invalid config: %s", msg)
        return 2

    symbols = None
    if args.symbols.strip():
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    try:
        _, _, report = run_backtest(days=args.days, symbols=symbols, config=config)
    except Exception:
        logger.exception("Backtest failed")
        return 1

    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
