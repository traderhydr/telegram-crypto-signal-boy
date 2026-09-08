"""Engine integration tests for volume + SMC skip reasons (no network)."""

from signal_bot.config import Config
from signal_bot.engine import SignalEngine
from signal_bot.models import Side


def _engine(**kwargs) -> SignalEngine:
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
        rsi_overbought=99.0,
        rsi_oversold=1.0,
    )
    defaults.update(kwargs)
    return SignalEngine(Config(**defaults), client=None)


def _mild_uptrend(n=120):
    closes = []
    price = 100.0
    for i in range(n):
        price += 0.15 if i % 5 != 4 else -0.05
        closes.append(price)
    highs = [c + 0.4 for c in closes]
    lows = [c - 0.4 for c in closes]
    opens = [c - 0.05 for c in closes]
    volumes = [10.0] * n
    return opens, highs, lows, closes, volumes


def test_volume_filter_skips_quiet_bar():
    opens, highs, lows, closes, volumes = _mild_uptrend()
    engine = _engine(filter_volume=True, vol_sma_period=20, vol_ratio_min=1.2)
    side, reason, *_ = engine.decide_direction(
        closes, highs=highs, lows=lows, volumes=volumes, opens=opens
    )
    assert side is None
    assert "volume" in reason.lower() or "rel_vol" in reason.lower()


def test_volume_filter_allows_spike():
    opens, highs, lows, closes, volumes = _mild_uptrend()
    volumes[-1] = 50.0
    engine = _engine(filter_volume=True, vol_sma_period=20, vol_ratio_min=1.2)
    side, reason, *_ = engine.decide_direction(
        closes, highs=highs, lows=lows, volumes=volumes, opens=opens
    )
    # May still fail other soft gates; if LONG, volume detail present
    if side is None:
        assert "skip" in reason.lower()
        # Should not fail on volume if spike is enough
        assert "rel_vol" not in reason or ">=" in reason or "volume" not in reason
    else:
        assert side == Side.LONG
        assert "rel_vol" in reason


def test_smc_skip_reason_prefix():
    opens, highs, lows, closes, volumes = _mild_uptrend(80)
    # Tiny ranges / no clear FVG — expect structure or fvg skip
    engine = _engine(
        filter_smc=True,
        filter_smc_structure=True,
        filter_smc_fvg=True,
        filter_smc_ob=False,
        filter_atr=True,
        atr_min_pct=0.01,
    )
    side, reason, *_ = engine.decide_direction(
        closes, highs=highs, lows=lows, volumes=volumes, opens=opens
    )
    if side is None:
        assert "skip" in reason.lower()
        assert (
            "structure" in reason.lower()
            or "fvg" in reason.lower()
            or "atr" in reason.lower()
            or "ohlc" in reason.lower()
            or "insufficient" in reason.lower()
        )
    else:
        assert "structure" in reason.lower() or "fvg" in reason.lower()


def test_missing_volume_skips_clearly():
    opens, highs, lows, closes, _ = _mild_uptrend()
    engine = _engine(filter_volume=True)
    side, reason, *_ = engine.decide_direction(
        closes, highs=highs, lows=lows, volumes=None, opens=opens
    )
    assert side is None
    assert "volume" in reason.lower()
