"""Unit tests for volume helpers (no network)."""

from signal_bot.volume import (
    obv,
    obv_slope,
    relative_volume,
    sma,
    volume_price_agreement,
    volume_ratio_ok,
)


def test_sma_basic():
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    out = sma(vals, 3)
    assert out[0] is None and out[1] is None
    assert out[2] == 2.0
    assert out[4] == 4.0


def test_relative_volume_spike():
    vols = [10.0] * 20 + [30.0]
    ratios = relative_volume(vols, 20)
    assert ratios[-1] is not None
    assert ratios[-1] == 30.0 / (sum(vols[-20:]) / 20)


def test_volume_ratio_ok_passes_on_spike():
    vols = [10.0] * 25 + [25.0]
    ok, detail = volume_ratio_ok(vols, period=20, min_ratio=1.2, confirm_bars=1)
    assert ok, detail
    assert "rel_vol" in detail


def test_volume_ratio_ok_fails_quiet():
    vols = [10.0] * 30
    ok, detail = volume_ratio_ok(vols, period=20, min_ratio=1.2)
    assert not ok
    assert "volume" in detail


def test_obv_rises_on_up_closes():
    closes = [100.0 + i for i in range(10)]
    volumes = [1.0] * 10
    series = obv(closes, volumes)
    assert series[-1] > series[0]
    slope = obv_slope(series, 5)
    assert slope is not None and slope > 0


def test_volume_price_agreement_long():
    closes = [100.0 + i for i in range(20)]
    volumes = [10.0 + i for i in range(20)]
    ok, detail = volume_price_agreement(closes, volumes, side_long=True, obv_lookback=5)
    assert ok, detail


def test_volume_price_agreement_short():
    closes = [100.0 - i for i in range(20)]
    volumes = [10.0 + i for i in range(20)]
    ok, detail = volume_price_agreement(closes, volumes, side_long=False, obv_lookback=5)
    assert ok, detail


def test_volume_price_agreement_blocks_wrong_obv():
    # Rising prices but force falling OBV via down-closes at end with huge vol... 
    # Simpler: rising closes always raise OBV — use falling closes for LONG fail
    closes = [100.0 - i * 0.5 for i in range(20)]
    volumes = [5.0] * 20
    ok, detail = volume_price_agreement(closes, volumes, side_long=True, obv_lookback=5)
    assert not ok
    assert "obv" in detail
