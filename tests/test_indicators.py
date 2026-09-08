"""Unit tests for EMA and RSI (no network)."""

from signal_bot.indicators import ema, last_valid, rsi


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
    # Strictly increasing closes → EMA rises after seed
    values = [float(i) for i in range(1, 31)]
    result = ema(values, 9)
    assert result[8] is not None
    assert result[-1] is not None
    assert result[-1] > result[8]
    # EMA should lag behind the last price
    assert result[-1] < values[-1]


def test_rsi_all_gains():
    # Strong uptrend → RSI near 100
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
    # Flat → avg_loss=0 after seed of zeros → RSI 100 by definition when al==0
    # With zero changes, gains=losses=0, al==0 → 100
    assert result[14] == 100.0


def test_last_valid():
    assert last_valid([None, None, 1.5, None]) == 1.5
    assert last_valid([None, None]) is None
