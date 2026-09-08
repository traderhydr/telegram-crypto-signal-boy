"""Unit tests for backtest simulation helpers (no network)."""

from signal_bot.backtest import (
    bar_touches_entry,
    r_for_exit,
    risk_unit,
    simulate_open_trade,
)
from signal_bot.models import Side


def _candle(o, h, l, c, t0=0, dt=900_000):
    return {
        "open_time": t0,
        "open": float(o),
        "high": float(h),
        "low": float(l),
        "close": float(c),
        "volume": 1.0,
        "close_time": t0 + dt - 1,
    }


def test_risk_unit_long_short():
    assert risk_unit(100.0, 95.0, Side.LONG) == 5.0
    assert risk_unit(100.0, 105.0, Side.SHORT) == 5.0


def test_r_for_exit_long_full_tp_and_sl():
    entry, sl = 100.0, 95.0
    assert abs(r_for_exit(entry, 105.0, sl, Side.LONG, 1.0) - 1.0) < 1e-9
    assert abs(r_for_exit(entry, sl, sl, Side.LONG, 1.0) - (-1.0)) < 1e-9
    assert abs(r_for_exit(entry, 105.0, sl, Side.LONG, 0.2) - 0.2) < 1e-9


def test_r_for_exit_short():
    entry, sl = 100.0, 105.0
    assert abs(r_for_exit(entry, 95.0, sl, Side.SHORT, 1.0) - 1.0) < 1e-9
    assert abs(r_for_exit(entry, sl, sl, Side.SHORT, 1.0) - (-1.0)) < 1e-9


def test_bar_touches_entry_long():
    c = _candle(101, 102, 99.5, 100.5)
    assert bar_touches_entry(c, 100.0, Side.LONG)
    assert not bar_touches_entry(c, 99.0, Side.LONG)
    assert bar_touches_entry(c, 99.5, Side.LONG)


def test_bar_touches_entry_short():
    c = _candle(99, 100.5, 98, 100)
    assert bar_touches_entry(c, 100.0, Side.SHORT)
    assert bar_touches_entry(c, 100.5, Side.SHORT)
    assert not bar_touches_entry(c, 101.0, Side.SHORT)


def test_simulate_long_all_tps():
    signal = _candle(100, 100.5, 99.5, 100.0, t0=0)
    bars = [signal]
    t = 900_000
    bars.append(_candle(100.2, 100.3, 99.9, 100.1, t0=t))
    t += 900_000
    for tp in (101, 102, 103, 104, 105):
        bars.append(_candle(tp - 0.5, tp + 0.1, tp - 1.0, tp, t0=t))
        t += 900_000

    tps = [101.0, 102.0, 103.0, 104.0, 105.0]
    result = simulate_open_trade(bars, Side.LONG, 100.0, tps, 95.0, 0)
    assert result.filled
    assert result.tps_hit == 5
    assert not result.stopped
    expected = 0.2 * sum((tp - 100.0) / 5.0 for tp in tps)
    assert abs(result.r_multiple - expected) < 1e-9


def test_simulate_long_sl_before_tp_same_bar_conservative():
    """Same bar touches SL and TP1 -> LONG assumes low (SL) first -> stopped."""
    signal = _candle(100, 100, 100, 100.0, t0=0)
    fill = _candle(100, 102, 94, 101, t0=900_000)
    tps = [101.0, 102.0, 103.0, 104.0, 105.0]
    result = simulate_open_trade([signal, fill], Side.LONG, 100.0, tps, 95.0, 0)
    assert result.filled
    assert result.stopped
    assert result.tps_hit == 0
    assert abs(result.r_multiple - (-1.0)) < 1e-9


def test_simulate_short_sl_before_tp_conservative():
    signal = _candle(100, 100, 100, 100.0, t0=0)
    fill = _candle(100, 106, 98, 99, t0=900_000)
    tps = [99.0, 98.0, 97.0, 96.0, 95.0]
    result = simulate_open_trade([signal, fill], Side.SHORT, 100.0, tps, 105.0, 0)
    assert result.filled
    assert result.stopped
    assert abs(result.r_multiple - (-1.0)) < 1e-9


def test_simulate_partial_tps_then_sl():
    signal = _candle(100, 100, 100, 100.0, t0=0)
    t = 900_000
    bars = [signal]
    bars.append(_candle(100, 100.2, 99.8, 100, t0=t))
    t += 900_000
    bars.append(_candle(100.5, 101.2, 100.4, 101, t0=t))
    t += 900_000
    bars.append(_candle(100, 100.5, 94, 95, t0=t))

    tps = [101.0, 102.0, 103.0, 104.0, 105.0]
    result = simulate_open_trade(bars, Side.LONG, 100.0, tps, 95.0, 0)
    assert result.filled
    assert result.stopped
    assert result.tps_hit == 1
    expected = 0.2 * (101.0 - 100.0) / 5.0 + 0.8 * (-1.0)
    assert abs(result.r_multiple - expected) < 1e-9


def test_entry_never_filled():
    signal = _candle(100, 100, 100, 100.0, t0=0)
    bars = [signal]
    t = 900_000
    for _ in range(5):
        bars.append(_candle(101, 102, 100.5, 101.5, t0=t))
        t += 900_000
    result = simulate_open_trade(
        bars, Side.LONG, 100.0, [101, 102, 103, 104, 105], 95.0, 0
    )
    assert not result.filled
    assert result.r_multiple == 0.0
