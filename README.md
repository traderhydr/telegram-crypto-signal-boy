# Telegram Crypto Signal Bot

Educational / informational trade-**signal** bot for Telegram. It reads **public** Binance USDT-M futures klines (no API keys, **no live trading**), applies EMA + RSI on 15m candles with **Fib / MACD / ATR / volume / SMC confluence filters** (ADX and SMC order-block optional; ADX and OB off by default), and posts LONG/SHORT signals with a 4-entry ladder, 5 take-profits, and 1 stop-loss.

> **Disclaimer:** This is not financial advice. Signals are for research/demo only. You are responsible for any trading decisions.

## Features

- Symbols: `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, `BNBUSDT`, `XRPUSDT`, `DOGEUSDT` (configurable)
- Leverage label: **10x** (configurable; informational only - bot does not place orders)
- Direction on **15m** candles by default (`INTERVAL`; `1h` supported as experimental alt — see [Backtest](#backtest))
- 4 configurable entry % offsets, 5 TP % targets, SL beyond the ladder
- Per-symbol/side cooldown (~5h default) to reduce spam
- Telegram Bot API -> channel; **dry-run** prints to stdout when `DRY_RUN=1` or tokens are missing
- **Historical backtester** for the same strategy (R-multiple metrics)

## Strategy rules

### Base direction (always on)

| Side | EMA | RSI |
|------|-----|-----|
| **LONG** | EMA9 > EMA21 | RSI14 < overbought (default 70) |
| **SHORT** | EMA9 < EMA21 | RSI14 > oversold (default 30) |

Mixed / choppy / RSI-filtered setups are **skipped** and logged.

### Confluence filters (default: Fib + MACD + ATR + Volume + SMC on; ADX/OB off)

Signals only fire when the base setup **and** every enabled filter agree.

#### 1. Fibonacci confluence (`FILTER_FIB=1`)

Documented in `indicators.find_swing` / `fib_confluence` and applied in `engine._apply_confluence`:

1. Take the last `FIB_LOOKBACK` bars (default **80**, typical 50-100).
2. `swing_high` = max(high) in the window; `swing_low` = min(low).
3. **Upswing** if the low occurs *before* the high (prior up move).  
   **Downswing** if the high occurs *before* the low (prior down move).
4. Default retracements **0.382 / 0.5 / 0.618** (`FIB_LEVELS`; prior best set — tighten via env if desired):
   - **LONG:** require an **upswing**; Fib *supports* = `high - ratio x (high - low)`. Price must be within tolerance of one of these (pullback into the zone).
   - **SHORT:** require a **downswing**; Fib *resistances* = `low + ratio x (high - low)`. Price must be within tolerance (bounce into the zone).
5. **Tolerance** = `max(price x FIB_TOL_PCT/100, ATR(14) x FIB_TOL_ATR)`  
   (defaults: 0.25% of price or 0.5xATR, whichever is larger).

#### 2. MACD confirmation (`FILTER_MACD=1`)

- Standard MACD **12 / 26 / 9**.
- **LONG:** MACD line > signal (histogram > 0).
- **SHORT:** MACD line < signal (histogram < 0).
- If MACD disagrees with the EMA side -> **skip**.

#### 3. ATR / volatility filter (`FILTER_ATR=1`)

- ATR(14); `ATR% = ATR / price x 100`.
- Skip if `ATR% < ATR_MIN_PCT` (default **0.15** - chop / dead market).
- Optionally skip if `ATR_MAX_PCT > 0` and `ATR%` exceeds it (default **0** = disabled).

#### 4. ADX trend-strength (`FILTER_ADX=0` by default)

- Wilder ADX(14); when enabled, only trade if `ADX >= ADX_MIN` (default **25**).
- Off by default; set `FILTER_ADX=1` to enable the trend gate.

#### 5. Volume filters (`FILTER_VOLUME=1`, `FILTER_OBV=1` by default)

Pragmatic volume gates in `signal_bot/volume.py` (not volume-profile / footprint):

1. **Relative volume** (`FILTER_VOLUME`): `vol_ratio = volume / SMA(volume, VOL_SMA_PERIOD)` (default SMA **20**).
   Require `vol_ratio >= VOL_RATIO_MIN` (default **1.2**) on the signal bar, or the max over the last `VOL_CONFIRM_BARS` bars (default **1**).
2. **OBV / volume-price agreement** (`FILTER_OBV`): On-Balance Volume slope over `OBV_LOOKBACK` (default **5**).
   - LONG: OBV slope > 0 (and not collapsing volume on an up-close).
   - SHORT: OBV slope < 0 (and not collapsing volume on a down-close).

Skip reasons are logged with a `volume:` / `obv:` prefix.

#### 6. SMC approximations (`FILTER_SMC=1` by default)

**Not a TradingView SMC clone.** Practical, testable definitions in `signal_bot/smc.py`:

1. **Market structure / BOS** (`FILTER_SMC_STRUCTURE=1`): fractal swing highs/lows (`SMC_SWING_LEFT/RIGHT`, default **3**). A **Break of Structure** is a close beyond the most recent confirmed unbroken swing high (bullish) or swing low (bearish). Require the latest BOS within `SMC_STRUCTURE_MAX_AGE` bars (default **40**) to align with the trade side. (First counter-trend BOS acts as CHoCH without a separate label.)
2. **Fair Value Gap** (`FILTER_SMC_FVG=1`): 3-candle imbalance — bullish if `low[i] > high[i-2]`, bearish if `high[i] < low[i-2]`. Require a recent **unfilled** directional FVG that price is inside / wick-touching / within `SMC_FVG_TOUCH_ATR * ATR` (default **0.35**).
3. **Order block** (`FILTER_SMC_OB=0` by default): last opposing candle before the impulsive move that created the aligned BOS; require price near the body zone within `SMC_OB_TOUCH_ATR * ATR` (default **0.5**). Optional to preserve sample size.

Skip reasons use `structure:` / `fvg:` / `ob:` prefixes.

### Signal format (unchanged)

Still **4 entries / 5 TPs / 10x** leverage label + 1 SL beyond the ladder.

## Project layout

```
signal_bot/
  __init__.py
  __main__.py
  config.py           # env-based settings (+ filter knobs)
  models.py           # Signal dataclass + message format
  binance_client.py   # public klines client (+ paginated history)
  indicators.py       # EMA, RSI, MACD, ATR, ADX, Fib helpers
  volume.py           # relative volume, OBV helpers
  smc.py              # practical BOS / FVG / order-block approximations
  levels.py           # entries / TPs / SL
  engine.py           # direction + confluence + cooldown + scan
  backtest_core.py    # fill simulation helpers
  backtest.py         # historical walk-forward backtester
  telegram_client.py  # Bot API + dry-run
  runner.py           # CLI
tests/
  test_indicators.py
  test_volume.py
  test_smc.py
  test_levels.py
  test_engine_direction.py
  test_engine_volume_smc.py
  test_backtest.py
.env.example
requirements.txt
pyproject.toml
```

## Setup

### 1. Clone & install

```bash
git clone https://github.com/traderhydr/telegram-crypto-signal-boy.git
cd telegram-crypto-signal-boy
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create a Telegram bot (BotFather)

1. Open Telegram and chat with [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** -> `TELEGRAM_BOT_TOKEN`

### 3. Channel admin

1. Create a public or private channel
2. Add your bot as an **administrator** with permission to post messages
3. Get the channel id:
   - Public: `@your_channel_username`
   - Private: forward a channel message to a bot like `@userinfobot`, or use the numeric id (often `-100...`)
4. Set `TELEGRAM_CHANNEL_ID`

### 4. Environment

```bash
cp .env.example .env
# Edit .env - for dry-run leave tokens empty and DRY_RUN=1
```

## Dry-run (recommended first)

```bash
export DRY_RUN=1
# or leave TELEGRAM_* unset
python -m signal_bot --once
```

Continuous loop (polls every `POLL_INTERVAL_SEC`):

```bash
python -m signal_bot
```

Live posting (tokens required, `DRY_RUN=0`):

```bash
export DRY_RUN=0
export TELEGRAM_BOT_TOKEN=your_token
export TELEGRAM_CHANNEL_ID=@your_channel
python -m signal_bot --once
```

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

#### Prior multi-coin baseline (Fib + MACD + ATR only; no volume/SMC)

~120 days, **default 6-symbol** universe, 15m:

| Symbol | Trades | Win% | Total R | MaxDD R | PF |
|--------|--------|------|---------|---------|----|
| BTCUSDT | 49 | 40.8% | -2.40 | 12.58 | 0.87 |
| ETHUSDT | 75 | 46.7% | +0.38 | 6.54 | 1.01 |
| SOLUSDT | 79 | 41.8% | -5.04 | 13.32 | 0.84 |
| BNBUSDT | 47 | 48.9% | +0.56 | 5.05 | 1.03 |
| XRPUSDT | 68 | 47.1% | +3.04 | 5.33 | 1.11 |
| DOGEUSDT | 78 | 47.4% | +3.09 | 4.94 | 1.11 |
| **COMBINED** | **396** | **45.5%** | **-0.37** | **28.77** | **1.00** |

#### Current defaults (+ Volume + SMC BOS/FVG; OB off)

| Symbol | Trades | Win% | Total R | MaxDD R | PF |
|--------|--------|------|---------|---------|----|
| BTCUSDT | 24 | 41.7% | -3.85 | 4.79 | 0.65 |
| ETHUSDT | 24 | 50.0% | +0.50 | 3.40 | 1.05 |
| SOLUSDT | 17 | 35.3% | -1.79 | 3.19 | 0.70 |
| BNBUSDT | 21 | 47.6% | -0.12 | 4.72 | 0.98 |
| XRPUSDT | 13 | 53.8% | +1.34 | 1.73 | 1.29 |
| DOGEUSDT | 23 | 47.8% | +2.13 | 3.40 | 1.24 |
| **COMBINED** | **122** | **45.9%** | **-1.79** | **13.05** | **0.96** |

vs prior multi-coin (Fib+MACD+ATR only): **396 / 45.5% / -0.37R / maxDD 28.77 / PF 1.00**.
Volume+SMC cuts trades ~3× and roughly halves maxDD, but **does not improve expectancy** (total R and PF slightly worse). Still not live-ready.


**Current defaults:** `SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT`, `FIB_LEVELS=0.382,0.5,0.618`, `FILTER_VOLUME=1`, `FILTER_OBV=1`, `FILTER_SMC=1`, `FILTER_SMC_OB=0`, `FILTER_ADX=0`, `INTERVAL=15m`. Still not live-ready on these metrics.

## Tests

```bash
pip install pytest
pytest -q
```

Tests cover indicators (incl. MACD/ATR/ADX/Fib), volume/SMC helpers, level generation, filter logic, and backtest simulation helpers **without network**.

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
| `FILTER_VOLUME` | `1` | Relative volume vs SMA |
| `VOL_SMA_PERIOD` / `VOL_RATIO_MIN` | `20` / `1.2` | Rel-vol gate |
| `VOL_CONFIRM_BARS` | `1` | Signal bar (or last N) |
| `FILTER_OBV` / `OBV_LOOKBACK` | `1` / `5` | OBV slope agreement |
| `FILTER_SMC` | `1` | Enable SMC stack (BOS+FVG) |
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

# Default confluence stack (Fib + MACD + ATR + Volume + SMC BOS/FVG; ADX/OB off)
FILTER_FIB=1 FILTER_MACD=1 FILTER_ATR=1 FILTER_VOLUME=1 FILTER_OBV=1 FILTER_SMC=1 FILTER_SMC_OB=0 FILTER_ADX=0 \
  python -m signal_bot.backtest --days 120

# Prior multi-coin baseline (no volume/SMC)
FILTER_VOLUME=0 FILTER_OBV=0 FILTER_SMC=0 python -m signal_bot.backtest --days 120

# Enable optional SMC order-block
FILTER_SMC_OB=1 python -m signal_bot.backtest --days 120

# Tighter Fib + enable ADX
FIB_LEVELS=0.5,0.618 FILTER_ADX=1 ADX_MIN=25 python -m signal_bot.backtest --days 120
```

## License

MIT
