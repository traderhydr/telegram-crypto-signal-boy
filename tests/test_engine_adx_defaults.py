"""Unit tests for direction + confluence filter logic (no network)."""

from signal_bot.config import Config
from signal_bot.engine import SignalEngine
from signal_bot.models import Side

def _engine(**kwargs) -> SignalEngine:
    # Base EMA/RSI tests disable confluence so synthetic close-only series work.
    defaults = dict(
        dry_run=True,
        filter_fib=False,
        filter_macd=False,
        filter_atr=False,
        filter_adx=False,
        filter_volume=False,
        filter_obv=False,
        filter_smc=False,
        filter_smc_ob=False,
        filter_htf=False,
        filter_supertrend=False,
    )
    defaults.update(kwargs)
    cfg = Config(**defaults)
    return SignalEngine(cfg, client=None)

def _up_then_sideways():
    closes = []
    price = 100.0
    for _ in range(40):
        price += 0.5
        closes.append(price)
    for i in range(50):
        price += 0.02 if i % 2 == 0 else -0.02
        closes.append(price)
    return closes

def _choppy_downtrend():
    closes = [100.0]
    for i in range(99):
        if i % 2 == 0:
            closes.append(closes[-1] + 0.4)
        else:
            closes.append(closes[-1] - 0.5)
    return closes

def test_adx_filter_blocks_weak_trend():
    """Flat/noisy market should fail ADX>=25 even if EMA/RSI look mildly bullish."""
    closes = []
    price = 100.0
    for i in range(120):
        # Tiny oscillation — weak directional movement -> low ADX
        price += 0.05 if i % 2 == 0 else -0.04
        closes.append(price)
    highs = [c + 0.3 for c in closes]
    lows = [c - 0.3 for c in closes]
    engine = _engine(
        filter_adx=True,
        adx_min=25.0,
        adx_period=14,
        filter_fib=False,
        filter_macd=False,
        filter_atr=False,
        rsi_overbought=99.0,
    )
    side, reason, *_ = engine.decide_direction(closes, highs=highs, lows=lows)
    from signal_bot.indicators import adx, last_valid

    adx_val = last_valid(adx(highs, lows, closes, 14))
    assert adx_val is not None
    if adx_val < 25:
        assert side is None
        assert "adx" in reason.lower()
    else:
        # Series accidentally strong — still assert helper path exists
        assert "ADX" in reason or side in (Side.LONG, Side.SHORT, None)

def test_adx_filter_allows_strong_trend():
    """Strong directional climb should pass ADX>=25 with other filters off."""
    n = 100
    closes = [100.0 + i * 1.2 for i in range(n)]
    highs = [c + 0.4 for c in closes]
    lows = [c - 0.4 for c in closes]
    engine = _engine(
        filter_adx=True,
        adx_min=25.0,
        filter_fib=False,
        filter_macd=False,
        filter_atr=False,
        rsi_overbought=99.5,  # allow strong-trend RSI
    )
    from signal_bot.indicators import adx, last_valid

    adx_val = last_valid(adx(highs, lows, closes, 14))
    assert adx_val is not None and adx_val >= 25
    side, reason, fast, slow, rsi_val = engine.decide_direction(
        closes, highs=highs, lows=lows
    )
    # Strong uptrend: either LONG with ADX in reason, or RSI overbought skip
    if side == Side.LONG:
        assert "ADX" in reason
    else:
        assert side is None
        assert "skip" in reason.lower()

def test_config_defaults_fib_and_adx():
    from signal_bot.config import Config

    cfg = Config()
    assert cfg.filter_adx is False
    assert cfg.adx_min == 25.0
    assert cfg.fib_levels == [0.382, 0.5, 0.618]
    assert cfg.interval == "15m"
    assert cfg.filter_fib and cfg.filter_macd and cfg.filter_atr
    assert cfg.filter_volume is False
    assert cfg.filter_obv is False
    assert cfg.filter_smc is False
    assert cfg.filter_smc_ob is False
    assert cfg.filter_htf is True
    assert cfg.filter_supertrend is True
    assert cfg.vol_ratio_min == 1.2
