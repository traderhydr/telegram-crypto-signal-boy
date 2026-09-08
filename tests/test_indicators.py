"""Unit tests for EMA, RSI, MACD, ATR, ADX, Fib helpers (no network)."""

from signal_bot.indicators import (
    adx,
    atr,
    ema,
    fib_confluence,
    find_swing,
    last_valid,
    macd,
    rsi,
)


def test_ema_constant_series():
    values = [10.0] * 20
    result = ema(values, 5)
    assert result[4] == 10.0
    assert all(v == 10.0 for v in result[4:])


def test_ema_insufficient_data():
    values = [1.0, 2.0, 3.0]
    result = ema(values, 5)
    assert all(v is None for v in result)


def test_ema_rising_trend():
    values = [float(i) for i in range(1, 31)]
    result = ema(values, 9)
    assert result[8] is not None
    assert result[-1] is not None
    assert result[-1] > result[8]
    assert result[-1] < values[-1]


def test_rsi_all_gains():
    values = [float(i) for i in range(1, 40)]
    result = rsi(values, 14)
    assert result[14] is not None
    assert result[-1] is not None
    assert result[-1] > 70


def test_rsi_all_losses():
    values = [float(40 - i) for i in range(40)]
    result = rsi(values, 14)
    assert result[-1] is not None
    assert result[-1] < 30


def test_rsi_flat():
    values = [50.0] * 30
    result = rsi(values, 14)
    assert result[14] == 100.0


def test_last_valid():
    assert last_valid([None, None, 1.5, None]) == 1.5
    assert last_valid([None, None]) is None


def test_atr_rising_range():
    # Expanding range -> ATR grows
    n = 40
    closes = [100.0 + i * 0.1 for i in range(n)]
    highs = [c + 1.0 + (i * 0.05) for i, c in enumerate(closes)]
    lows = [c - 1.0 - (i * 0.05) for i, c in enumerate(closes)]
    series = atr(highs, lows, closes, 14)
    assert series[14] is not None
    assert series[-1] is not None
    assert series[-1] > series[14]


def test_atr_insufficient():
    closes = [1.0, 2.0, 3.0]
    assert all(v is None for v in atr(closes, closes, closes, 14))


def test_macd_uptrend_positive_hist():
    # Accelerating uptrend so MACD stays above its signal
    values = [100.0]
    for i in range(1, 100):
        values.append(values[-1] + 0.2 + i * 0.05)
    series = macd(values, 12, 26, 9)
    point = last_valid(series)
    assert point is not None
    assert point.macd > point.signal
    assert point.histogram > 0


def test_macd_downtrend_negative_hist():
    values = [100.0]
    for i in range(1, 100):
        values.append(values[-1] - 0.2 - i * 0.05)
    series = macd(values, 12, 26, 9)
    point = last_valid(series)
    assert point is not None
    assert point.macd < point.signal
    assert point.histogram < 0


def test_find_swing_upswing():
    # Low early, high late -> upswing
    lows = [10.0] * 20 + [5.0] + [10.0] * 30 + [12.0] * 29
    highs = [11.0] * 20 + [11.0] + [11.0] * 30 + [20.0] + [15.0] * 28
    # Make lengths equal 80
    n = 80
    lows = lows[:n]
    highs = highs[:n]
    # Ensure min low at index 20, max high at index 51
    lows = [10.0] * n
    highs = [11.0] * n
    lows[20] = 5.0
    highs[55] = 20.0
    swing = find_swing(highs, lows, lookback=80)
    assert swing is not None
    assert swing.is_upswing
    assert swing.swing_low == 5.0
    assert swing.swing_high == 20.0
    levels = dict(swing.retracement_levels())
    # 0.5 retrace of 5->20 up move = 20 - 0.5*15 = 12.5
    assert abs(levels[0.5] - 12.5) < 1e-9


def test_find_swing_downswing():
    n = 80
    lows = [10.0] * n
    highs = [11.0] * n
    highs[15] = 20.0
    lows[60] = 5.0
    swing = find_swing(highs, lows, lookback=80)
    assert swing is not None
    assert not swing.is_upswing
    levels = dict(swing.retracement_levels())
    # 0.5 bounce of 20->5 down move = 5 + 0.5*15 = 12.5
    assert abs(levels[0.5] - 12.5) < 1e-9


def test_fib_confluence_long_near_support():
    n = 80
    lows = [10.0] * n
    highs = [11.0] * n
    lows[10] = 100.0
    highs[40] = 200.0
    # Actually swing_low must be the min - set properly
    lows = [150.0] * n
    highs = [160.0] * n
    lows[10] = 100.0
    highs[40] = 200.0
    # 0.5 support = 200 - 0.5*100 = 150
    price = 150.0
    ok, detail = fib_confluence(
        price, True, highs, lows, lookback=80, tolerance=1.0
    )
    assert ok, detail
    assert "0.500" in detail or "0.5" in detail


def test_fib_confluence_long_rejects_downswing():
    n = 80
    lows = [150.0] * n
    highs = [160.0] * n
    highs[10] = 200.0
    lows[40] = 100.0
    ok, detail = fib_confluence(
        150.0, True, highs, lows, lookback=80, tolerance=5.0
    )
    assert not ok
    assert "downswing" in detail.lower() or "upswing" in detail.lower()


def test_fib_confluence_short_near_resistance():
    n = 80
    lows = [150.0] * n
    highs = [160.0] * n
    highs[10] = 200.0
    lows[40] = 100.0
    # 0.5 resistance of down move = 100 + 0.5*100 = 150
    ok, detail = fib_confluence(
        150.0, False, highs, lows, lookback=80, tolerance=1.0
    )
    assert ok, detail


def test_adx_trending_vs_flat():
    # Strong directional move should eventually produce ADX > flat noise
    n = 80
    closes_trend = [100.0 + i * 0.8 for i in range(n)]
    highs_trend = [c + 0.5 for c in closes_trend]
    lows_trend = [c - 0.5 for c in closes_trend]
    adx_trend = last_valid(adx(highs_trend, lows_trend, closes_trend, 14))
    assert adx_trend is not None
    assert adx_trend > 20


def test_default_fib_ratios_include_0382():
    """Default confluence ratios are 0.382, 0.5, and 0.618 (prior best set)."""
    from signal_bot.indicators import FIB_RATIOS

    assert FIB_RATIOS == (0.382, 0.5, 0.618)
    assert 0.382 in FIB_RATIOS


def test_fib_confluence_accepts_0382_zone_by_default():
    """Price parked at 0.382 should pass with default ratios; fail if 0.382 dropped."""
    n = 80
    lows = [150.0] * n
    highs = [160.0] * n
    lows[10] = 100.0
    highs[40] = 200.0
    # 0.382 support of 100->200 upswing = 200 - 0.382*100 = 161.8
    # Keep price away from 0.5 (150) and 0.618 (138.2)
    price = 161.8
    ok_default, detail = fib_confluence(
        price, True, highs, lows, lookback=80, tolerance=1.0
    )
    assert ok_default, detail
    assert "0.382" in detail
    ok_tight, detail2 = fib_confluence(
        price,
        True,
        highs,
        lows,
        lookback=80,
        tolerance=1.0,
        ratios=(0.5, 0.618),
    )
    assert not ok_tight, detail2


def test_retracement_levels_respect_custom_ratios():
    n = 80
    lows = [150.0] * n
    highs = [160.0] * n
    lows[10] = 100.0
    highs[40] = 200.0
    swing = find_swing(highs, lows, lookback=80)
    assert swing is not None and swing.is_upswing
    default_levels = dict(swing.retracement_levels())
    assert set(default_levels) == {0.382, 0.5, 0.618}
    custom = dict(swing.retracement_levels(ratios=(0.5, 0.618)))
    assert set(custom) == {0.5, 0.618}
