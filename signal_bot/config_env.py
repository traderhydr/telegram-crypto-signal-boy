"""Env loading and validation helpers for Config (split for push size)."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Tuple

from .config import DEFAULT_SYMBOLS, _parse_bool, _parse_float_list, _parse_symbols

if TYPE_CHECKING:
    from .config import Config


def config_from_env(cls: type) -> "Config":
    dry_env = os.getenv("DRY_RUN", "1").strip().lower()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    channel = os.getenv("TELEGRAM_CHANNEL_ID", "").strip()
    dry_run = dry_env in ("1", "true", "yes") or not token or not channel
    return cls(
        symbols=_parse_symbols(os.getenv("SYMBOLS", ",".join(DEFAULT_SYMBOLS))),
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
        filter_adx=_parse_bool(os.getenv("FILTER_ADX"), False),
        fib_lookback=int(os.getenv("FIB_LOOKBACK", "80")),
        fib_tol_pct=float(os.getenv("FIB_TOL_PCT", "0.25")),
        fib_tol_atr=float(os.getenv("FIB_TOL_ATR", "0.5")),
        fib_levels=_parse_float_list(os.getenv("FIB_LEVELS", ""), [0.382, 0.5, 0.618]),
        macd_fast=int(os.getenv("MACD_FAST", "12")),
        macd_slow=int(os.getenv("MACD_SLOW", "26")),
        macd_signal=int(os.getenv("MACD_SIGNAL", "9")),
        atr_period=int(os.getenv("ATR_PERIOD", "14")),
        atr_min_pct=float(os.getenv("ATR_MIN_PCT", "0.15")),
        atr_max_pct=float(os.getenv("ATR_MAX_PCT", "0")),
        adx_period=int(os.getenv("ADX_PERIOD", "14")),
        adx_min=float(os.getenv("ADX_MIN", "25")),
        filter_volume=_parse_bool(os.getenv("FILTER_VOLUME"), False),
        vol_sma_period=int(os.getenv("VOL_SMA_PERIOD", "20")),
        vol_ratio_min=float(os.getenv("VOL_RATIO_MIN", "1.2")),
        vol_confirm_bars=int(os.getenv("VOL_CONFIRM_BARS", "1")),
        filter_obv=_parse_bool(os.getenv("FILTER_OBV"), False),
        obv_lookback=int(os.getenv("OBV_LOOKBACK", "5")),
        filter_smc=_parse_bool(os.getenv("FILTER_SMC"), False),
        filter_smc_structure=_parse_bool(os.getenv("FILTER_SMC_STRUCTURE"), True),
        filter_smc_fvg=_parse_bool(os.getenv("FILTER_SMC_FVG"), True),
        filter_smc_ob=_parse_bool(os.getenv("FILTER_SMC_OB"), False),
        smc_swing_left=int(os.getenv("SMC_SWING_LEFT", "3")),
        smc_swing_right=int(os.getenv("SMC_SWING_RIGHT", "3")),
        smc_structure_max_age=int(os.getenv("SMC_STRUCTURE_MAX_AGE", "40")),
        smc_fvg_lookback=int(os.getenv("SMC_FVG_LOOKBACK", "60")),
        smc_fvg_touch_atr=float(os.getenv("SMC_FVG_TOUCH_ATR", "0.35")),
        smc_ob_lookback=int(os.getenv("SMC_OB_LOOKBACK", "15")),
        smc_ob_touch_atr=float(os.getenv("SMC_OB_TOUCH_ATR", "0.5")),
        smc_ob_max_age=int(os.getenv("SMC_OB_MAX_AGE", "40")),
        filter_htf=_parse_bool(os.getenv("FILTER_HTF"), True),
        htf_interval=os.getenv("HTF_INTERVAL", "4h").strip() or "4h",
        htf_ema_fast=int(os.getenv("HTF_EMA_FAST", "20")),
        htf_ema_slow=int(os.getenv("HTF_EMA_SLOW", "50")),
        htf_kline_limit=int(os.getenv("HTF_KLINE_LIMIT", "120")),
        filter_supertrend=_parse_bool(os.getenv("FILTER_SUPERTREND"), True),
        supertrend_period=int(os.getenv("SUPERTREND_PERIOD", "10")),
        supertrend_multiplier=float(os.getenv("SUPERTREND_MULTIPLIER", "3")),
        entry_offsets_pct=_parse_float_list(os.getenv("ENTRY_OFFSETS_PCT", ""), [0.0, -0.3, -0.6, -1.0]),
        tp_targets_pct=_parse_float_list(os.getenv("TP_TARGETS_PCT", ""), [0.5, 1.0, 1.5, 2.5, 4.0]),
        sl_beyond_ladder_pct=float(os.getenv("SL_BEYOND_LADDER_PCT", "0.5")),
        cooldown_hours=float(os.getenv("COOLDOWN_HOURS", "5")),
        poll_interval_sec=int(os.getenv("POLL_INTERVAL_SEC", "60")),
        telegram_bot_token=token,
        telegram_channel_id=channel,
        dry_run=dry_run,
        binance_futures_base=os.getenv("BINANCE_FUTURES_BASE", "https://fapi.binance.com").rstrip("/"),
    )


def validate_config(self: "Config") -> Tuple[bool, str]:
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
    if self.vol_sma_period < 2:
        return False, "VOL_SMA_PERIOD must be >= 2"
    if self.vol_ratio_min <= 0:
        return False, "VOL_RATIO_MIN must be > 0"
    if self.vol_confirm_bars < 1:
        return False, "VOL_CONFIRM_BARS must be >= 1"
    if self.obv_lookback < 1:
        return False, "OBV_LOOKBACK must be >= 1"
    if self.smc_swing_left < 1 or self.smc_swing_right < 1:
        return False, "SMC_SWING_LEFT/RIGHT must be >= 1"
    if self.htf_ema_fast >= self.htf_ema_slow:
        return False, "HTF_EMA_FAST must be less than HTF_EMA_SLOW"
    if self.supertrend_period < 1:
        return False, "SUPERTREND_PERIOD must be >= 1"
    if self.supertrend_multiplier <= 0:
        return False, "SUPERTREND_MULTIPLIER must be > 0"
    if self.kline_limit < self.warmup_bars():
        return False, (
            f"KLINE_LIMIT ({self.kline_limit}) < warmup_bars "
            f"({self.warmup_bars()}); raise KLINE_LIMIT"
        )
    return True, "ok"
