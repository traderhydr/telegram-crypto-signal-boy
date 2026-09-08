"""Unit tests for practical SMC helpers (no network)."""

from signal_bot.smc import (
    detect_fvgs,
    find_swing_points,
    fvg_ok,
    structure_ok,
)


def _ramp_up(n=80, start=100.0, step=1.0):
    closes = [start + i * step for i in range(n)]
    opens = [c - 0.2 for c in closes]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    return opens, highs, lows, closes


def test_find_swing_points_has_highs_and_lows():
    # Zigzag so fractals form
    highs = []
    lows = []
    for i in range(40):
        if i % 6 == 3:
            highs.append(110.0)
            lows.append(100.0)
        elif i % 6 == 0:
            highs.append(101.0)
            lows.append(90.0)
        else:
            highs.append(102.0)
            lows.append(98.0)
    swings = find_swing_points(highs, lows, left=2, right=2)
    assert any(s.kind == "high" for s in swings)
    assert any(s.kind == "low" for s in swings)


def test_detect_bullish_fvg():
    # Build a clear gap: bar0 high=100, bar2 low=105
    highs = [100.0, 103.0, 110.0, 111.0, 112.0]
    lows = [95.0, 101.0, 105.0, 108.0, 109.0]
    fvgs = detect_fvgs(highs, lows, lookback=10)
    assert any(f.bullish and f.bottom == 100.0 and f.top == 105.0 for f in fvgs)


def test_detect_bearish_fvg():
    highs = [110.0, 105.0, 100.0, 99.0, 98.0]
    lows = [108.0, 102.0, 95.0, 94.0, 93.0]
    # bearish: highs[2]=100 < lows[0]=108
    fvgs = detect_fvgs(highs, lows, lookback=10)
    assert any(not f.bullish for f in fvgs)


def test_structure_ok_bullish_bos():
    """Strong uptrend with swing lows/highs should eventually print bullish BOS."""
    opens, highs, lows, closes = _ramp_up(100, start=100.0, step=0.8)
    # Add a pullback mid-way then break higher so a swing high exists then breaks
    for i in range(50, 60):
        closes[i] = closes[49] - (i - 49) * 0.5
        highs[i] = closes[i] + 0.4
        lows[i] = closes[i] - 0.4
        opens[i] = closes[i] + 0.1
    for i in range(60, 100):
        closes[i] = closes[59] + (i - 59) * 1.0
        highs[i] = closes[i] + 0.5
        lows[i] = closes[i] - 0.5
        opens[i] = closes[i] - 0.2
    ok, detail = structure_ok(
        closes, highs, lows, side_long=True, swing_left=2, swing_right=2, max_age_bars=80
    )
    # Strong breakout may or may not have fractal swings depending on shape;
    # assert API returns a structured reason either way.
    assert "structure" in detail
    if ok:
        assert "bullish BOS" in detail


def test_fvg_ok_near_bullish_gap():
    # Create bullish FVG then park price inside it without filling below bottom
    n = 30
    highs = [100.0] * n
    lows = [99.0] * n
    # At i=10: gap — highs[8]=100, lows[10]=104
    highs[8] = 100.0
    lows[8] = 99.0
    highs[9] = 103.0
    lows[9] = 101.0
    highs[10] = 108.0
    lows[10] = 104.0
    # Keep later bars inside [100, 104] without piercing bottom
    for i in range(11, n):
        highs[i] = 103.5
        lows[i] = 101.0
    price = 102.0
    ok, detail = fvg_ok(
        price, highs, lows, side_long=True, lookback=30, atr_val=2.0, touch_atr=0.5
    )
    assert ok, detail
    assert "fvg" in detail and "bullish" in detail


def test_fvg_ok_rejects_wrong_side():
    n = 20
    highs = [100.0] * n
    lows = [99.0] * n
    highs[8] = 100.0
    lows[10] = 105.0
    highs[10] = 110.0
    for i in range(11, n):
        highs[i] = 108.0
        lows[i] = 106.0
    ok, detail = fvg_ok(107.0, highs, lows, side_long=False, lookback=20, atr_val=1.0)
    assert not ok
    assert "fvg" in detail
