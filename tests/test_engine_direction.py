"""Unit tests for direction logic (no network)."""

from signal_bot.config import Config
from signal_bot.engine import SignalEngine
from signal_bot.models import Side


def _engine(**kwargs) -> SignalEngine:
    cfg = Config(dry_run=True, **kwargs)
    return SignalEngine(cfg, client=None)  # client unused for decide_direction


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
    # Net down with frequent bounces so RSI stays > 30 while EMA fast < slow
    closes = [100.0]
    for i in range(99):
        if i % 2 == 0:
            closes.append(closes[-1] + 0.4)
        else:
            closes.append(closes[-1] - 0.5)
    return closes


def test_long_when_fast_above_slow_and_rsi_ok():
    engine = _engine()
    side, reason, fast, slow, rsi_val = engine.decide_direction(_up_then_sideways())
    assert side == Side.LONG, f"expected LONG got {side}: {reason} rsi={rsi_val}"
    assert fast > slow
    assert rsi_val < 70


def test_short_when_fast_below_slow_and_rsi_ok():
    engine = _engine()
    side, reason, fast, slow, rsi_val = engine.decide_direction(_choppy_downtrend())
    assert side == Side.SHORT, f"expected SHORT got {side}: {reason} rsi={rsi_val}"
    assert fast < slow
    assert rsi_val > 30


def test_skip_overbought_bullish():
    closes = [100.0 + i * 2.0 for i in range(80)]
    engine = _engine()
    side, reason, *_ = engine.decide_direction(closes)
    assert side is None
    assert "overbought" in reason.lower() or "skip" in reason.lower()


def test_skip_when_insufficient_data():
    engine = _engine()
    side, reason, *_ = engine.decide_direction([1.0, 2.0, 3.0])
    assert side is None
    assert "insufficient" in reason.lower()
