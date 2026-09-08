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


DEFAULT_SYMBOLS: List[str] = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT",
]


def _parse_symbols(raw: str) -> List[str]:
    raw = (raw or "").strip()
    if not raw:
        return list(DEFAULT_SYMBOLS)
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def _parse_bool(raw: str, default: bool) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    """Runtime configuration for the signal bot."""

    symbols: List[str] = field(default_factory=lambda: list(DEFAULT_SYMBOLS))
    interval: str = "15m"
    leverage: int = 10
    kline_limit: int = 200
    ema_fast: int = 9
    ema_slow: int = 21
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    # Fib+MACD+ATR+HTF+ST on; ADX/Vol/SMC off
    filter_fib: bool = True
    filter_macd: bool = True
    filter_atr: bool = True
    filter_adx: bool = False
    fib_lookback: int = 80
    fib_tol_pct: float = 0.25
    fib_tol_atr: float = 0.5
    fib_levels: List[float] = field(default_factory=lambda: [0.382, 0.5, 0.618])
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    atr_period: int = 14
    atr_min_pct: float = 0.15
    atr_max_pct: float = 0.0
    adx_period: int = 14
    adx_min: float = 25.0
    filter_volume: bool = False
    vol_sma_period: int = 20
    vol_ratio_min: float = 1.2
    vol_confirm_bars: int = 1
    filter_obv: bool = False
    obv_lookback: int = 5
    filter_smc: bool = False
    filter_smc_structure: bool = True
    filter_smc_fvg: bool = True
    filter_smc_ob: bool = False
    smc_swing_left: int = 3
    smc_swing_right: int = 3
    smc_structure_max_age: int = 40
    smc_fvg_lookback: int = 60
    smc_fvg_touch_atr: float = 0.35
    smc_ob_lookback: int = 15
    smc_ob_touch_atr: float = 0.5
    smc_ob_max_age: int = 40
    # HTF ON: 4h EMA20/50
    filter_htf: bool = True
    htf_interval: str = "4h"
    htf_ema_fast: int = 20
    htf_ema_slow: int = 50
    htf_kline_limit: int = 120
    # Supertrend ON: 10 x 3
    filter_supertrend: bool = True
    supertrend_period: int = 10
    supertrend_multiplier: float = 3.0
    entry_offsets_pct: List[float] = field(default_factory=lambda: [0.0, -0.3, -0.6, -1.0])
    tp_targets_pct: List[float] = field(default_factory=lambda: [0.5, 1.0, 1.5, 2.5, 4.0])
    sl_beyond_ladder_pct: float = 0.5
    cooldown_hours: float = 5.0
    poll_interval_sec: int = 60
    telegram_bot_token: str = ""
    telegram_channel_id: str = ""
    dry_run: bool = True
    binance_futures_base: str = "https://fapi.binance.com"

    def warmup_bars(self) -> int:
        macd_need = self.macd_slow + self.macd_signal
        adx_need = 2 * self.adx_period + 1 if self.filter_adx else 0
        fib_need = self.fib_lookback if self.filter_fib else 0
        vol_need = self.vol_sma_period + 1 if self.filter_volume else 0
        obv_need = self.obv_lookback + 2 if self.filter_obv else 0
        smc_need = 0
        if self.filter_smc:
            smc_need = max(
                self.smc_swing_left + self.smc_swing_right + 5,
                self.smc_fvg_lookback if self.filter_smc_fvg else 0,
                self.smc_structure_max_age + 10,
            )
        st_need = self.supertrend_period + 1 if self.filter_supertrend else 0
        return max(
            self.ema_slow, self.rsi_period + 1, self.atr_period + 1,
            macd_need, adx_need, fib_need, vol_need, obv_need, smc_need, st_need, 50,
        )

    @classmethod
    def from_env(cls) -> "Config":
        from .config_env import config_from_env
        return config_from_env(cls)

    def validate(self) -> Tuple[bool, str]:
        from .config_env import validate_config
        return validate_config(self)
