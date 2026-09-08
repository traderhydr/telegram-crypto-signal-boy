"""CLI runner: one-shot scan, continuous poll loop, or backtest."""

from __future__ import annotations

import argparse
import logging
import sys
import time

from .config import Config
from .engine import SignalEngine
from .telegram_client import TelegramClient


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_once(engine: SignalEngine, tg: TelegramClient) -> int:
    signals = engine.scan()
    if not signals:
        logging.getLogger(__name__).info("No new signals this scan")
        return 0
    for sig in signals:
        tg.send_signal(sig)
    return len(signals)


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Telegram crypto trade-signal bot (public Binance data only)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan and exit (default: continuous loop)",
    )
    parser.add_argument(
        "--backtest",
        action="store_true",
        help="Run historical backtest instead of live scanning",
    )
    parser.add_argument(
        "--days",
        type=float,
        default=120.0,
        help="Backtest lookback days (with --backtest; default: 120)",
    )
    parser.add_argument(
        "--symbols",
        type=str,
        default="",
        help="Comma-separated symbols override (live or backtest)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args(argv)

    setup_logging(args.verbose)
    log = logging.getLogger(__name__)

    if args.backtest:
        from .backtest import main as backtest_main

        bt_argv = ["--days", str(args.days)]
        if args.symbols.strip():
            bt_argv.extend(["--symbols", args.symbols])
        if args.verbose:
            bt_argv.append("-v")
        return backtest_main(bt_argv)

    config = Config.from_env()
    ok, msg = config.validate()
    if not ok:
        log.error("Invalid config: %s", msg)
        return 2

    if args.symbols.strip():
        config.symbols = [
            s.strip().upper() for s in args.symbols.split(",") if s.strip()
        ]

    log.info(
        "Starting bot symbols=%s interval=%s leverage=%sx dry_run=%s",
        config.symbols,
        config.interval,
        config.leverage,
        config.dry_run,
    )

    engine = SignalEngine(config)
    tg = TelegramClient(
        bot_token=config.telegram_bot_token,
        channel_id=config.telegram_channel_id,
        dry_run=config.dry_run,
    )

    if args.once:
        run_once(engine, tg)
        return 0

    while True:
        try:
            run_once(engine, tg)
        except KeyboardInterrupt:
            log.info("Interrupted, shutting down")
            return 0
        except Exception:
            log.exception("Scan failed; will retry")
        time.sleep(config.poll_interval_sec)


if __name__ == "__main__":
    sys.exit(main())
