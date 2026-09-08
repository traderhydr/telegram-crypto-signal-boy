"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Tuple

from dotenv import load_dotenv

load_dotenv()


def _parse_float_list(raw: str, default: List[float]) -> List[float]:
    raw = (raw or "").strip()
    if not raw:
        return list(default)
    return [float(x.strip()) for x in raw.split(",") if x.strip()]


def _parse_symbols(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return ["BTCUSDT", "ETHUSDT"]
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


@dataclass
class Config:
    """Runtime configuration for the signal bot."""

    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    interval: str = "15m"
    leverage: int = 10
    kline_limit: int = 200

    # EMA / RSI
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0

    # Entry ladder: % offsets from reference (signed by side in engine)
    # LONG: buy dips → negative offsets; SHORT: sell rips → positive offsets
    entry_offsets_pct: List[float] = field(
        default_factory=lambda: [0.0, -0.3, -0.6, -1.0]
    )
    # TP % targets from reference (absolute; engine applies direction)
    tp_targets_pct: List[float] = field(
        default_factory=lambda: [0.5, 1.0, 1.5, 2.5, 4.0]
    )
    # SL % beyond the farthest entry of the ladder
    sl_beyond_ladder_pct: float = 0.5

    # Cooldown hours per symbol/side
    cooldown_hours: float = 5.0

    # Poll interval seconds between scans
    poll_interval_sec: int = 60

    # Telegram
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    dry_run: bool = True

    # Binance public futures base URL (USDT-M)
    binance_futures_base: str = "https://fapi.binance.com"

    @classmethod
    def from_env(cls) -> "Config":
        dry_env = os.getenv("DRY_RUN", "1").strip().lower()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        channel = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
        # Dry-run if explicitly set, or if tokens are missing
        dry_run = dry_env in ("1", "true", "yes") or not token or not channel

        return cls(
            symbols=_parse_symbols(os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT")),
            interval=os.getenv("INTERVAL", "15m").strip() or "15m",
            leverage=int(os.getenv("LEVERAGE", "10")),
            kline_limit=int(os.getenv("KLINE_LIMIT", "200")),
            ema_fast=int(os.getenv("EMA_FAST", "9")),
            ema_slow=int(os.getenv("EMA_SLOW", "21")),
            rsi_period=int(os.getenv("RSI_PERIOD", "14")),
            rsi_overbought=float(os.getenv("RSI_OVERBOUGHT", "70")),
            rsi_oversold=float(os.getenv("RSI_OVERSOLD", "30")),
            entry_offsets_pct=_parse_float_list(
                os.getenv("ENTRY_OFFSETS_PCT", ""),
                [0.0, -0.3, -0.6, -1.0],
            ),
            tp_targets_pct=_parse_float_list(
                os.getenv("TP_TARGETS_PCT", ""),
                [0.5, 1.0, 1.5, 2.5, 4.0],
            ),
            sl_beyond_ladder_pct=float(os.getenv("SL_BEYOND_LADDER_PCT", "0.5")),
            cooldown_hours=float(os.getenv("COOLDOWN_HOURS", "5")),
            poll_interval_sec=int(os.getenv("POLL_INTERVAL_SEC", "60")),
            telegram_bot_token=token,
            telegram_channel_id=channel,
            dry_run=dry_run,
            binance_futures_base=os.getenv(
                "BINANCE_FUTURES_BASE", "https://fapi.binance.com"
            ).rstrip("/"),
        )

    def validate(self) -> Tuple[bool, str]:
        if len(self.entry_offsets_pct) != 4:
            return False, "ENTRY_OFFSETS_PCT must have exactly 4 values"
        if len(self.tp_targets_pct) != 5:
            return False, "TP_TARGETS_PCT must have exactly 5 values"
        if self.ema_fast >= self.ema_slow:
            return False, "EMA_FAST must be less than EMA_SLOW"
        if self.leverage < 1:
            return False, "LEVERAGE must be >= 1"
        return True, "ok"
