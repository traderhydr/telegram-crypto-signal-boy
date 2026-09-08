"""Unit tests for entry / TP / SL level generation (no network)."""

import pytest

from signal_bot.levels import generate_levels
from signal_bot.models import Side, Signal


ENTRY_OFFSETS = [0.0, -0.3, -0.6, -1.0]
TP_TARGETS = [0.5, 1.0, 1.5, 2.5, 4.0]
SL_BEYOND = 0.5
REF = 100_000.0


def test_long_entries_are_at_or_below_ref():
    entries, tps, sl = generate_levels(
        REF, Side.LONG, ENTRY_OFFSETS, TP_TARGETS, SL_BEYOND
    )
    assert len(entries) == 4
    assert len(tps) == 5
    assert entries[0] == REF  # 0% offset
    assert entries[1] < REF
    assert entries[-1] == pytest.approx(REF * 0.99, rel=1e-6)
    # TPs above ref
    assert all(tp > REF for tp in tps)
    # SL below farthest entry
    assert sl < min(entries)


def test_short_entries_are_at_or_above_ref():
    entries, tps, sl = generate_levels(
        REF, Side.SHORT, ENTRY_OFFSETS, TP_TARGETS, SL_BEYOND
    )
    assert len(entries) == 4
    assert entries[0] == REF
    assert entries[1] > REF  # mirrored offsets → rips
    assert all(tp < REF for tp in tps)
    assert sl > max(entries)


def test_sl_beyond_ladder_long():
    entries, _, sl = generate_levels(
        REF, Side.LONG, ENTRY_OFFSETS, TP_TARGETS, SL_BEYOND
    )
    farthest = min(entries)
    expected = farthest * (1 - SL_BEYOND / 100)
    assert sl == pytest.approx(expected, rel=1e-6)


def test_sl_beyond_ladder_short():
    entries, _, sl = generate_levels(
        REF, Side.SHORT, ENTRY_OFFSETS, TP_TARGETS, SL_BEYOND
    )
    farthest = max(entries)
    expected = farthest * (1 + SL_BEYOND / 100)
    assert sl == pytest.approx(expected, rel=1e-6)


def test_tp_count_and_ordering_long():
    _, tps, _ = generate_levels(REF, Side.LONG, ENTRY_OFFSETS, TP_TARGETS, SL_BEYOND)
    assert tps == sorted(tps)
    assert tps[0] == pytest.approx(REF * 1.005, rel=1e-6)
    assert tps[-1] == pytest.approx(REF * 1.04, rel=1e-6)


def test_invalid_entry_count():
    with pytest.raises(ValueError, match="exactly 4"):
        generate_levels(REF, Side.LONG, [0.0, -0.5], TP_TARGETS, SL_BEYOND)


def test_invalid_tp_count():
    with pytest.raises(ValueError, match="exactly 5"):
        generate_levels(REF, Side.LONG, ENTRY_OFFSETS, [1.0, 2.0], SL_BEYOND)


def test_signal_format_message_contains_fields():
    entries, tps, sl = generate_levels(
        REF, Side.LONG, ENTRY_OFFSETS, TP_TARGETS, SL_BEYOND
    )
    sig = Signal(
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entries=entries,
        take_profits=tps,
        stop_loss=sl,
        rationale="EMA9>EMA21 and RSI=55.0<70",
        reference_price=REF,
    )
    msg = sig.format_message()
    assert "LONG" in msg
    assert "BTCUSDT" in msg
    assert "10x" in msg
    assert "Stop loss" in msg
    assert "TP1" in msg
    assert "Entry 1" in msg
