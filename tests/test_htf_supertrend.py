"""Unit tests for Supertrend + HTF EMA bias helpers (no network)."""

from signal_bot.config import Config
from signal_bot.engine import SignalEngine
from signal_bot.indicators import (
    completed_htf_closes,
    htf_ema_bias,
    last_valid,
    resample_klines_to_htf,
    supertrend,
    supertrend_agrees,
)
from signal_bot.models import Side


def test_supertrend_uptrend_bullish():
    n = 80
    closes = [100.0 + i * 0.8 for i in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    series = supertrend(highs, lows, closes, period=10, multiplier=3.0)
    point = last_valid(series)
    assert point is not None
    assert point.direction == 1
    ok, detail = supertrend_agrees(highs, lows, closes, side_long=True)
    assert ok, detail
    ok_short, detail_s = supertrend_agrees(highs, lows, closes, side_long=False)
    assert not ok_short
    assert "bullish" in detail_s.lower()


def test_supertrend_downtrend_bearish():
    n = 80
    closes = [200.0 - i * 0.8 for i in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    point = last_valid(supertrend(highs, lows, closes, period=10, multiplier=3.0))
    assert point is not None
    assert point.direction == -1
    ok, detail = supertrend_agrees(highs, lows, closes, side_long=False)
    assert ok, detail
    ok_long, detail_l = supertrend_agrees(highs, lows, closes, side_long=True)
    assert not ok_long


def test_supertrend_insufficient_data():
    closes = [1.0, 2.0, 3.0]
    series = supertrend(closes, closes, closes, period=10)
    assert all(v is None for v in series)
    ok, detail = supertrend_agrees(closes, closes, closes, side_long=True)
    assert not ok
    assert "insufficient" in detail.lower()


def test_htf_ema_bias_long_requires_fast_above_slow():
    # Rising series -> EMA20 > EMA50
    closes = [100.0 + i * 0.5 for i in range(80)]
    ok, detail = htf_ema_bias(closes, side_long=True, fast=20, slow=50)
    assert ok, detail
    assert "bull" in detail.lower()
    ok_short, detail_s = htf_ema_bias(closes, side_long=False, fast=20, slow=50)
    assert not ok_short
    assert "bullish" in detail_s.lower()


def test_htf_ema_bias_short_requires_fast_below_slow():
    closes = [200.0 - i * 0.5 for i in range(80)]
    ok, detail = htf_ema_bias(closes, side_long=False, fast=20, slow=50)
    assert ok, detail
    assert "bear" in detail.lower()
    ok_long, detail_l = htf_ema_bias(closes, side_long=True, fast=20, slow=50)
    assert not ok_long


def test_htf_ema_bias_insufficient():
    ok, detail = htf_ema_bias([1.0, 2.0, 3.0], side_long=True, fast=20, slow=50)
    assert not ok
    assert "insufficient" in detail.lower()


def test_resample_klines_to_htf_15m_to_4h():
    # 16 x 15m = one 4h bucket (900_000 * 16 = 14_400_000)
    htf_ms = 14_400_000
    ltf_ms = 900_000
    candles = []
    base = 1_700_000_000_000  # aligned-ish
    base = (base // htf_ms) * htf_ms
    for i in range(32):
        ot = base + i * ltf_ms
        candles.append(
            {
                "open_time": ot,
                "close_time": ot + ltf_ms - 1,
                "open": 100.0 + i,
                "high": 110.0 + i,
                "low": 90.0 + i,
                "close": 105.0 + i,
                "volume": 1.0,
            }
        )
    htf = resample_klines_to_htf(candles, htf_ms)
    assert len(htf) == 2
    assert htf[0]["open"] == 100.0
    assert htf[0]["close"] == 105.0 + 15
    assert htf[0]["high"] == max(110.0 + i for i in range(16))
    assert htf[0]["low"] == min(90.0 + i for i in range(16))
    assert htf[0]["volume"] == 16.0


def test_completed_htf_closes_excludes_forming():
    htf = [
        {"close_time": 100, "close": 1.0},
        {"close_time": 200, "close": 2.0},
        {"close_time": 300, "close": 3.0},
    ]
    assert completed_htf_closes(htf, 200) == [1.0, 2.0]
    assert completed_htf_closes(htf, 199) == [1.0]


def test_engine_htf_filter_blocks_disagreeing_long():
    # Mild LTF uptrend but force bearish HTF closes
    closes = []
    price = 100.0
    for i in range(80):
        price += 0.3 if i % 4 != 3 else -0.05
        closes.append(price)
    highs = [c + 0.4 for c in closes]
    lows = [c - 0.4 for c in closes]
    htf_closes = [200.0 - i * 0.5 for i in range(80)]  # bearish HTF
    cfg = Config(
        dry_run=True,
        filter_fib=False,
        filter_macd=False,
        filter_atr=False,
        filter_adx=False,
        filter_volume=False,
        filter_obv=False,
        filter_smc=False,
        filter_supertrend=False,
        filter_htf=True,
        htf_ema_fast=20,
        htf_ema_slow=50,
        rsi_overbought=99.0,
    )
    engine = SignalEngine(cfg, client=None)
    side, reason, *_ = engine.decide_direction(
        closes, highs=highs, lows=lows, htf_closes=htf_closes
    )
    assert side is None
    assert "htf" in reason.lower()


def test_engine_supertrend_filter_blocks_against_trend():
    # Downtrend: Supertrend bearish should block LONG if somehow candidate;
    # with EMA also bearish we expect SHORT path or skip.
    closes = [200.0 - i * 0.6 for i in range(80)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    cfg = Config(
        dry_run=True,
        filter_fib=False,
        filter_macd=False,
        filter_atr=False,
        filter_adx=False,
        filter_volume=False,
        filter_obv=False,
        filter_smc=False,
        filter_htf=False,
        filter_supertrend=True,
        supertrend_period=10,
        supertrend_multiplier=3.0,
        rsi_oversold=1.0,
    )
    engine = SignalEngine(cfg, client=None)
    side, reason, *_ = engine.decide_direction(closes, highs=highs, lows=lows)
    # SHORT should be allowed if Supertrend bearish; LONG must not pass
    if side == Side.SHORT:
        assert "Supertrend" in reason or "bear" in reason.lower()
    else:
        assert side is None
        assert "skip" in reason.lower()


def test_config_defaults_htf_supertrend_and_vol_off():
    cfg = Config()
    assert cfg.filter_volume is False
    assert cfg.filter_obv is False
    assert cfg.filter_smc is False
    assert cfg.filter_smc_ob is False
    assert cfg.filter_htf is True
    assert cfg.filter_supertrend is True
    assert cfg.htf_interval == "4h"
    assert cfg.htf_ema_fast == 20
    assert cfg.htf_ema_slow == 50
    assert cfg.supertrend_period == 10
    assert cfg.supertrend_multiplier == 3.0
    assert cfg.filter_fib and cfg.filter_macd and cfg.filter_atr
    assert cfg.filter_adx is False
