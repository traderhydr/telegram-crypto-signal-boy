"""CLI entry for backtest."""
from __future__ import annotations
import argparse
import logging
import sys
from typing import List, Optional

from .backtest_run import format_report, run_backtest
from .config import Config

logger = logging.getLogger(__name__)

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
