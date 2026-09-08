"""Backtest simulation helpers (pure, no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .models import Side


@dataclass
class TradeResult:
    symbol: str
    side: Side
    signal_time: datetime
    entry_time: Optional[datetime]
    exit_time: Optional[datetime]
    entry_price: float
    stop_loss: float
    take_profits: List[float]
    r_multiple: float
    tps_hit: int
    stopped: bool
    filled: bool
    reason: str = ""


@dataclass
class SymbolMetrics:
    symbol: str
    trades: int = 0
    wins: int = 0
    losses: int = 0
    total_r: float = 0.0
    gross_profit_r: float = 0.0
    gross_loss_r: float = 0.0
    max_drawdown_r: float = 0.0
    equity_curve: List[float] = field(default_factory=list)
    trade_results: List[TradeResult] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return (self.wins / self.trades * 100.0) if self.trades else 0.0

    @property
    def avg_r(self) -> float:
        return self.total_r / self.trades if self.trades else 0.0

    @property
    def profit_factor(self) -> float:
        if self.gross_loss_r == 0:
            return float("inf") if self.gross_profit_r > 0 else 0.0
        return self.gross_profit_r / abs(self.gross_loss_r)


def _ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def risk_unit(entry: float, stop_loss: float, side: Side) -> float:
    """Absolute price distance that equals 1R."""
    if side == Side.LONG:
        risk = entry - stop_loss
    else:
        risk = stop_loss - entry
    if risk <= 0:
        raise ValueError(f"invalid risk: entry={entry} sl={stop_loss} side={side}")
    return risk


def r_for_exit(
    entry: float, exit_price: float, stop_loss: float, side: Side, size: float
) -> float:
    """R-multiple for a partial (or full) exit of ``size`` (fraction of 1.0)."""
    risk = risk_unit(entry, stop_loss, side)
    if side == Side.LONG:
        return size * (exit_price - entry) / risk
    return size * (entry - exit_price) / risk


def bar_touches_entry(candle: Dict[str, Any], entry: float, side: Side) -> bool:
    """True if this bar's high/low range touches Entry1 (incl. exact touch)."""
    if side == Side.LONG:
        return candle["low"] <= entry
    return candle["high"] >= entry


def simulate_open_trade(
    candles: Sequence[Dict[str, Any]],
    side: Side,
    entry1: float,
    take_profits: Sequence[float],
    stop_loss: float,
    signal_index: int,
) -> TradeResult:
    """Simulate one trade after the signal bar; see README for path rules."""
    symbol = ""
    signal_time = _ms_to_dt(candles[signal_index]["close_time"])
    tps = list(take_profits)
    tp_size = 1.0 / len(tps)
    remaining = 1.0
    tps_hit = 0
    total_r = 0.0
    entry_time: Optional[datetime] = None
    exit_time: Optional[datetime] = None
    in_position = False

    for j in range(signal_index + 1, len(candles)):
        c = candles[j]
        bar_time = _ms_to_dt(c["close_time"])

        if not in_position:
            if bar_touches_entry(c, entry1, side):
                in_position = True
                entry_time = bar_time
            else:
                continue

        high, low = c["high"], c["low"]

        if side == Side.LONG:
            if low <= stop_loss:
                total_r += r_for_exit(entry1, stop_loss, stop_loss, side, remaining)
                remaining = 0.0
                exit_time = bar_time
                return TradeResult(
                    symbol=symbol, side=side, signal_time=signal_time,
                    entry_time=entry_time, exit_time=exit_time,
                    entry_price=entry1, stop_loss=stop_loss, take_profits=tps,
                    r_multiple=total_r, tps_hit=tps_hit, stopped=True,
                    filled=True, reason="stopped",
                )
            while tps_hit < len(tps) and high >= tps[tps_hit]:
                total_r += r_for_exit(entry1, tps[tps_hit], stop_loss, side, tp_size)
                remaining -= tp_size
                tps_hit += 1
                exit_time = bar_time
                if remaining <= 1e-12:
                    remaining = 0.0
                    return TradeResult(
                        symbol=symbol, side=side, signal_time=signal_time,
                        entry_time=entry_time, exit_time=exit_time,
                        entry_price=entry1, stop_loss=stop_loss, take_profits=tps,
                        r_multiple=total_r, tps_hit=tps_hit, stopped=False,
                        filled=True, reason="all_tps",
                    )
        else:
            if high >= stop_loss:
                total_r += r_for_exit(entry1, stop_loss, stop_loss, side, remaining)
                remaining = 0.0
                exit_time = bar_time
                return TradeResult(
                    symbol=symbol, side=side, signal_time=signal_time,
                    entry_time=entry_time, exit_time=exit_time,
                    entry_price=entry1, stop_loss=stop_loss, take_profits=tps,
                    r_multiple=total_r, tps_hit=tps_hit, stopped=True,
                    filled=True, reason="stopped",
                )
            while tps_hit < len(tps) and low <= tps[tps_hit]:
                total_r += r_for_exit(entry1, tps[tps_hit], stop_loss, side, tp_size)
                remaining -= tp_size
                tps_hit += 1
                exit_time = bar_time
                if remaining <= 1e-12:
                    remaining = 0.0
                    return TradeResult(
                        symbol=symbol, side=side, signal_time=signal_time,
                        entry_time=entry_time, exit_time=exit_time,
                        entry_price=entry1, stop_loss=stop_loss, take_profits=tps,
                        r_multiple=total_r, tps_hit=tps_hit, stopped=False,
                        filled=True, reason="all_tps",
                    )

    if not in_position:
        return TradeResult(
            symbol=symbol, side=side, signal_time=signal_time,
            entry_time=None, exit_time=None, entry_price=entry1,
            stop_loss=stop_loss, take_profits=tps, r_multiple=0.0,
            tps_hit=0, stopped=False, filled=False, reason="entry_not_filled",
        )

    last = candles[-1]
    mtm = r_for_exit(entry1, last["close"], stop_loss, side, remaining)
    total_r += mtm
    return TradeResult(
        symbol=symbol, side=side, signal_time=signal_time,
        entry_time=entry_time, exit_time=_ms_to_dt(last["close_time"]),
        entry_price=entry1, stop_loss=stop_loss, take_profits=tps,
        r_multiple=total_r, tps_hit=tps_hit, stopped=False,
        filled=True, reason="end_of_data_mtm",
    )


def update_metrics(m: SymbolMetrics, trade: TradeResult) -> None:
    if not trade.filled:
        return
    m.trades += 1
    m.total_r += trade.r_multiple
    m.trade_results.append(trade)
    if trade.r_multiple > 0:
        m.wins += 1
        m.gross_profit_r += trade.r_multiple
    elif trade.r_multiple < 0:
        m.losses += 1
        m.gross_loss_r += trade.r_multiple
    prev = m.equity_curve[-1] if m.equity_curve else 0.0
    m.equity_curve.append(prev + trade.r_multiple)
    peak = 0.0
    dd = 0.0
    for r in m.equity_curve:
        peak = max(peak, r)
        dd = max(dd, peak - r)
    m.max_drawdown_r = dd
