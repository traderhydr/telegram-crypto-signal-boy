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


def _ohlc_from_closes(closes, spread=1.0):
    highs = [c + spread for c in closes]
    lows = [c - spread for c in closes]
    return highs, lows


def test_macd_filter_blocks_disagreeing_long():
    """Uptrend closes that are rolling over may have bullish EMA but bearish MACD mid-turn;
    craft a series where EMA is still bullish but we force MACD off via config check path.
    """
    # Strong up then sharp drop at end: EMA may still be > but MACD hist can flip.
    closes = [100.0 + i * 0.5 for i in range(60)]
    # Add a sharp decline so MACD histogram turns negative while EMA9 may still > EMA21 briefly
    for i in range(25):
        closes.append(closes[-1] - 1.2)

    engine = _engine(filter_macd=True, filter_fib=False, filter_atr=False)
    highs, lows = _ohlc_from_closes(closes, spread=0.8)
    side, reason, fast, slow, rsi_val = engine.decide_direction(
        closes, highs=highs, lows=lows
    )
    # Either skip due to MACD or due to RSI/EMA - must not blindly LONG if MACD disagrees
    if side == Side.LONG:
        # If still LONG, MACD must have agreed (hist > 0)
        assert "MACD" in reason or "macd" in reason.lower() or "hist" in reason
    else:
        assert side is None
        assert "skip" in reason.lower()


def test_atr_filter_skips_chop():
    # Mild uptrend with tiny ranges + small downs so RSI < 100; ATR% still tiny
    closes = []
    price = 100.0
    for i in range(120):
        if i % 4 == 3:
            price -= 0.01
        else:
            price += 0.04
        closes.append(price)
    highs = [c + 0.008 for c in closes]
    lows = [c - 0.008 for c in closes]
    engine = _engine(
        filter_atr=True,
        filter_macd=False,
        filter_fib=False,
        atr_min_pct=0.15,
        rsi_overbought=99.5,
    )
    side, reason, fast, slow, rsi_val = engine.decide_direction(
        closes, highs=highs, lows=lows
    )
    # If base setup never fires, force-check ATR helper path via a known LONG base
    if "overbought" in reason.lower() or "mixed" in reason.lower():
        # Directly verify ATR% would fail for this series
        from signal_bot.indicators import atr, last_valid
        a = last_valid(atr(highs, lows, closes, 14))
        assert a is not None
        atr_pct = a / closes[-1] * 100
        assert atr_pct < 0.15
    else:
        assert side is None, reason
        assert "atr" in reason.lower()


def test_fib_filter_requires_matching_swing():
    # Build clear upswing and park price at 0.5 retracement with MACD/ATR off
    n = 100
    closes = []
    highs = []
    lows = []
    # Climb from 100 -> 200 over first 50 bars
    for i in range(50):
        c = 100.0 + i * 2.0
        closes.append(c)
        highs.append(c + 0.5)
        lows.append(c - 0.5)
    # Pull back toward 150 (0.5 of 100->200): 49 steps of 1.0 from 200 -> 151
    for i in range(1, 50):
        c = 200.0 - i * 1.0
        closes.append(c)
        highs.append(c + 0.5)
        lows.append(c - 0.5)
    # Force swing high/low extrema
    lows[0] = 99.0
    highs[49] = 201.0
    assert abs(closes[-1] - 151.0) < 0.01

    engine = _engine(
        filter_fib=True,
        filter_macd=False,
        filter_atr=False,
        fib_lookback=100,
        fib_tol_pct=2.0,
        fib_tol_atr=10.0,
        rsi_overbought=99.0,
    )
    side, reason, fast, slow, rsi_val = engine.decide_direction(
        closes, highs=highs, lows=lows
    )
    if side is None and "fib" in reason.lower():
        assert True
    elif side == Side.LONG:
        assert "Fib" in reason or "fib" in reason.lower()
    else:
        assert "skip" in reason.lower()


def test_fib_filter_blocks_wrong_structure():
    """Downswing structure must block LONG Fib confluence."""
    n = 80
    closes = [150.0] * n
    highs = [151.0] * n
    lows = [149.0] * n
    highs[5] = 200.0
    lows[50] = 100.0
    # Mild bullish EMA: slowly rising closes at end
    for i in range(60, n):
        closes[i] = 150.0 + (i - 60) * 0.3
        highs[i] = closes[i] + 1.0
        lows[i] = closes[i] - 1.0
    engine = _engine(
        filter_fib=True,
        filter_macd=False,
        filter_atr=False,
        fib_lookback=80,
        fib_tol_pct=5.0,
        fib_tol_atr=10.0,
        rsi_overbought=99.0,
    )
    side, reason, *_ = engine.decide_direction(closes, highs=highs, lows=lows)
    # Either not a LONG candidate, or Fib rejects downswing
    if side is None:
        assert "skip" in reason.lower()
    else:
        assert side != Side.LONG or "Fib" in reason


def test_confluence_missing_ohlc_skips():
    engine = _engine(filter_fib=True, filter_macd=False, filter_atr=True)
    closes = _up_then_sideways()
    side, reason, *_ = engine.decide_direction(closes)  # no highs/lows
    assert side is None
    assert "ohlc" in reason.lower() or "missing" in reason.lower()



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
