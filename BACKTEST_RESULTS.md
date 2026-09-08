# Backtest results

## Backtest

Walk-forward backtest of the **same** live rules (EMA/RSI + enabled confluence filters), levels, and cooldown. Fetches paginated public Binance USDT-M klines for the configured interval (~120 days by default; falls back to `www.binance.com` if `fapi` returns 451).

**Live default remains `INTERVAL=15m`.** `1h` is an optional / experimental alternate timeframe — use env or CLI override; do not assume it is better without checking the latest report.

```bash
# Default 15m + default 6-symbol universe (INTERVAL / SYMBOLS from Config)
python -m signal_bot.backtest --days 120
# or:
python -m signal_bot --backtest --days 120

# Override symbols / experimental 1h timeframe
python -m signal_bot.backtest --days 120 --symbols BTCUSDT,ETHUSDT
python -m signal_bot.backtest --days 120 --interval 1h
INTERVAL=1h python -m signal_bot.backtest --days 120
python -m signal_bot --backtest --days 120 --interval 1h
```

### Simulation assumptions

| Rule | Detail |
|------|--------|
| Reference | Close of the signal bar |
| Levels | `generate_levels` / Config defaults (4 entries, 5 TPs, 1 SL) |
| Entry fill | Position opens when a **later** bar's range touches **Entry1**; size = 1.0 unit notional |
| Exits | Equal size across 5 TPs (20% each); remaining size stopped at SL |
| Intra-bar path | **Conservative**: LONG checks low (SL) before high (TPs); SHORT checks high (SL) before low (TPs) |
| Cooldown | Same as live: per symbol/side after a signal is emitted |
| Overlap | At most one open simulated position per symbol |
| Metrics | R-multiples where 1R = \|Entry1 - SL\| |

### Recent filtered results (reference)

> **Honesty:** stacking more indicators is not the same as finding an edge. Volume+SMC made results *worse*. The current defaults test **HTF bias + Supertrend** on top of Fib+MACD+ATR (volume/SMC off). Treat any single ~120d window as exploratory, not proof.

#### Prior multi-coin baseline (Fib + MACD + ATR only)

~120 days, default 6 symbols, 15m: **COMBINED 396 trades / 45.5% WR / -0.37R / MaxDD 28.77 / PF 1.00**.

#### Prior experiment (+ Volume + SMC; worse expectancy)

| COMBINED | 122 | 45.9% | **-1.79R** | 13.05 | **0.96** |

#### Current defaults (Fib + MACD + ATR + HTF EMA20/50@4h + Supertrend 10×3; Vol/SMC off)

~120 days, default 6-symbol universe, 15m (see `backtest_report.txt`):

| Symbol | Trades | Win% | Total R | MaxDD R | PF |
|--------|--------|------|---------|---------|----|
| BTCUSDT | 30 | 50.0% | +1.34 | 4.40 | 1.14 |
| ETHUSDT | 49 | 40.8% | +1.66 | 5.46 | 1.09 |
| SOLUSDT | 54 | 44.4% | -3.81 | 11.27 | 0.85 |
| BNBUSDT | 37 | 35.1% | -8.74 | 11.54 | 0.54 |
| XRPUSDT | 45 | 48.9% | +6.52 | 6.15 | 1.39 |
| DOGEUSDT | 51 | 45.1% | +5.80 | 4.99 | 1.36 |
| **COMBINED** | **266** | **44.0%** | **+2.77** | **26.87** | **1.03** |

vs prior Fib+MACD+ATR baseline (**396 / 45.5% / -0.37R / maxDD 28.8 / PF 1.00**): fewer trades, slightly better total R and PF, still near break-even. SOL/BNB remain large drag. **Not live-ready.**

#### Ablation (same window, Fib+MACD+ATR base)

| Stack | Trades | Win% | Total R | MaxDD R | PF |
|-------|--------|------|---------|---------|----|
| Fib+MACD+ATR only | 395 | 44.8% | -2.14 | 28.94 | 0.99 |
| + HTF only | 302 | 46.4% | **+13.56** | **19.08** | **1.12** |
| + Supertrend only | 367 | 43.9% | -6.80 | 29.56 | 0.95 |
| + HTF + Supertrend (defaults) | 264 | 43.6% | +0.31 | 26.87 | 1.00 |

**Takeaway:** HTF bias helped in this window; Supertrend alone hurt; combining them diluted the HTF gain back toward flat. Defaults keep both ON as requested for further testing — consider `FILTER_SUPERTREND=0` if optimizing for this sample. Indicators still do not guarantee an edge.

**Current defaults:** `INTERVAL=15m`, Fib+MACD+ATR ON, `FILTER_HTF=1` (4h EMA20/50), `FILTER_SUPERTREND=1` (10, 3), `FILTER_VOLUME=0`, `FILTER_OBV=0`, `FILTER_SMC=0`, `FILTER_SMC_OB=0`, `FILTER_ADX=0`. Same 6 symbols.

## Tests

```bash
pip install pytest
pytest -q
```

Tests cover indicators (incl. MACD/ATR/ADX/Fib/Supertrend/HTF), volume/SMC helpers, level generation, filter logic, and backtest simulation helpers **without network**.

## Configuration cheat sheet

| Variable | Default | Notes |
|----------|---------|-------|
| `SYMBOLS` | `BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT` | Comma-separated |
| `INTERVAL` | `15m` | Binance interval (`15m` live default; `1h` experimental via env/`--interval`) |
| `LEVERAGE` | `10` | Label only |
| `EMA_FAST` / `EMA_SLOW` | `9` / `21` | |
| `RSI_*` | `14` / `70` / `30` | |
| `FILTER_FIB` | `1` | Fib confluence |
| `FILTER_MACD` | `1` | MACD confirmation |
| `FILTER_ATR` | `1` | ATR% chop/extreme gate |
| `FILTER_ADX` | `0` | ADX(14) trend-strength gate (off by default) |
| `FILTER_HTF` | `1` | 4h EMA bias (default EMA20/50) |
| `HTF_INTERVAL` / `HTF_EMA_FAST` / `HTF_EMA_SLOW` | `4h` / `20` / `50` | HTF bias params |
| `FILTER_SUPERTREND` | `1` | ATR Supertrend direction gate |
| `SUPERTREND_PERIOD` / `SUPERTREND_MULTIPLIER` | `10` / `3` | Supertrend params |
| `FILTER_VOLUME` | `0` | Relative volume vs SMA (off by default) |
| `VOL_SMA_PERIOD` / `VOL_RATIO_MIN` | `20` / `1.2` | Rel-vol gate |
| `VOL_CONFIRM_BARS` | `1` | Signal bar (or last N) |
| `FILTER_OBV` / `OBV_LOOKBACK` | `0` / `5` | OBV slope agreement (off by default) |
| `FILTER_SMC` | `0` | Enable SMC stack (BOS+FVG; off by default) |
| `FILTER_SMC_STRUCTURE` / `FILTER_SMC_FVG` | `1` / `1` | Core SMC pieces |
| `FILTER_SMC_OB` | `0` | Optional order-block gate |
| `SMC_SWING_LEFT/RIGHT` | `3` / `3` | Fractal swing size |
| `SMC_STRUCTURE_MAX_AGE` | `40` | Max bars since aligned BOS |
| `SMC_FVG_LOOKBACK` / `SMC_FVG_TOUCH_ATR` | `60` / `0.35` | FVG search / proximity |
| `FIB_LOOKBACK` | `80` | Swing window (bars) |
| `FIB_LEVELS` | `0.382,0.5,0.618` | Fib confluence ratios (prior best) |
| `FIB_TOL_PCT` / `FIB_TOL_ATR` | `0.25` / `0.5` | Proximity tolerance |
| `MACD_FAST/SLOW/SIGNAL` | `12/26/9` | |
| `ATR_PERIOD` / `ATR_MIN_PCT` / `ATR_MAX_PCT` | `14` / `0.15` / `0` | `0` max = off |
| `ADX_PERIOD` / `ADX_MIN` | `14` / `25` | Used when `FILTER_ADX=1` |
| `ENTRY_OFFSETS_PCT` | `0,-0.3,-0.6,-1.0` | Exactly 4 |
| `TP_TARGETS_PCT` | `0.5,1.0,1.5,2.5,4.0` | Exactly 5 |
| `SL_BEYOND_LADDER_PCT` | `0.5` | Beyond farthest entry |
| `COOLDOWN_HOURS` | `5` | Per symbol/side |
| `DRY_RUN` | `1` | Forced if tokens missing |

### Toggling filters

```bash
# Baseline EMA+RSI only (previous behaviour)
FILTER_FIB=0 FILTER_MACD=0 FILTER_ATR=0 FILTER_ADX=0 python -m signal_bot.backtest --days 120

# Default confluence stack (Fib + MACD + ATR + HTF + Supertrend; Vol/SMC/ADX off)
FILTER_FIB=1 FILTER_MACD=1 FILTER_ATR=1 FILTER_HTF=1 FILTER_SUPERTREND=1 \
  FILTER_VOLUME=0 FILTER_OBV=0 FILTER_SMC=0 FILTER_ADX=0 \
  python -m signal_bot.backtest --days 120

# Prior Fib+MACD+ATR baseline (no HTF/ST/Vol/SMC)
FILTER_HTF=0 FILTER_SUPERTREND=0 FILTER_VOLUME=0 FILTER_OBV=0 FILTER_SMC=0 \
  python -m signal_bot.backtest --days 120

# Ablation: HTF only (no Supertrend)
FILTER_SUPERTREND=0 python -m signal_bot.backtest --days 120

# Ablation: Supertrend only (no HTF)
FILTER_HTF=0 python -m signal_bot.backtest --days 120

# Re-enable volume/SMC experiment
FILTER_VOLUME=1 FILTER_OBV=1 FILTER_SMC=1 python -m signal_bot.backtest --days 120

# Tighter Fib + enable ADX
FIB_LEVELS=0.5,0.618 FILTER_ADX=1 ADX_MIN=25 python -m signal_bot.backtest --days 120
```

## License

MIT
