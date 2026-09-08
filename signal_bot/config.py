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


def _parse_bool(raw: str, default: bool) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    """Runtime configuration for the signal bot."""

    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    interval: str = "15m"
    leverage: int = 10
    kline_limit: int = 200

    # EMA / RSI (base direction)
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0

    # --- Confluence filters (default: Fib + MACD + ATR + ADX) ---
    filter_fib: bool = True
    filter_macd: bool = True
    filter_atr: bool = True
    filter_adx: bool = True  # ADX(14) trend-strength gate

    # Fibonacci
    fib_lookback: int = 80  # bars for swing high/low (50-100 typical)
    # Absolute proximity = max(price * fib_tol_pct/100, atr * fib_tol_atr)
    fib_tol_pct: float = 0.25  # % of price
    fib_tol_atr: float = 0.5  # fraction of ATR(14)
    # Confluence ratios (tightened default: 0.5 + 0.618 only; drop 0.382)
    fib_levels: List[float] = field(default_factory=lambda: [0.5, 0.618])

    # MACD 12/26/9
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    # ATR volatility filter
    atr_period: int = 14
    atr_min_pct: float = 0.15  # skip if ATR/price*100 < this (chop)
    atr_max_pct: float = 0.0  # 0 = disabled; else skip if ATR% above this

    # ADX trend-strength gate (on by default)
    adx_period: int = 14
    adx_min: float = 25.0

    # Entry ladder: % offsets from reference (signed by side in engine)
    # LONG: buy dips -> negative offsets; SHORT: sell rips -> positive offsets
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

    def warmup_bars(self) -> int:
        """Minimum bars needed before indicators / Fib lookback are usable."""
        macd_need = self.macd_slow + self.macd_signal
        adx_need = 2 * self.adx_period + 1 if self.filter_adx else 0
        fib_need = self.fib_lookback if self.filter_fib else 0
        return max(
            self.ema_slow,
            self.rsi_period + 1,
            self.atr_period + 1,
            macd_need,
            adx_need,
            fib_need,
            50,
        )

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
            filter_fib=_parse_bool(os.getenv("FILTER_FIB"), True),
            filter_macd=_parse_bool(os.getenv("FILTER_MACD"), True),
            filter_atr=_parse_bool(os.getenv("FILTER_ATR"), True),
            filter_adx=_parse_bool(os.getenv("FILTER_ADX"), True),
            fib_lookback=int(os.getenv("FIB_LOOKBACK", "80")),
            fib_tol_pct=float(os.getenv("FIB_TOL_PCT", "0.25")),
            fib_tol_atr=float(os.getenv("FIB_TOL_ATR", "0.5")),
            fib_levels=_parse_float_list(
                os.getenv("FIB_LEVELS", ""),
                [0.5, 0.618],
            ),
            macd_fast=int(os.getenv("MACD_FAST", "12")),
            macd_slow=int(os.getenv("MACD_SLOW", "26")),
            macd_signal=int(os.getenv("MACD_SIGNAL", "9")),
            atr_period=int(os.getenv("ATR_PERIOD", "14")),
            atr_min_pct=float(os.getenv("ATR_MIN_PCT", "0.15")),
            atr_max_pct=float(os.getenv("ATR_MAX_PCT", "0")),
            adx_period=int(os.getenv("ADX_PERIOD", "14")),
            adx_min=float(os.getenv("ADX_MIN", "25")),
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
        if self.macd_fast >= self.macd_slow:
            return False, "MACD_FAST must be less than MACD_SLOW"
        if self.fib_lookback < 10:
            return False, "FIB_LOOKBACK must be >= 10"
        if not self.fib_levels:
            return False, "FIB_LEVELS must have at least one ratio"
        if any(r <= 0 or r >= 1 for r in self.fib_levels):
            return False, "FIB_LEVELS ratios must be in (0, 1)"
        if self.kline_limit < self.warmup_bars():
            return (
                False,
                f"KLINE_LIMIT ({self.kline_limit}) < warmup_bars "
                f"({self.warmup_bars()}); raise KLINE_LIMIT",
            )
        return True, "ok"
