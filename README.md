# Telegram Crypto Signal Bot

Educational / informational trade-**signal** bot for Telegram. It reads **public** Binance USDT-M futures klines (no API keys, **no live trading**), applies EMA + RSI on 15m candles with **Fib / MACD / ATR confluence filters**, and posts LONG/SHORT signals with a 4-entry ladder, 5 take-profits, and 1 stop-loss.

> **Disclaimer:** This is not financial advice. Signals are for research/demo only. You are responsible for any trading decisions.

## Features

- Symbols: `BTCUSDT`, `ETHUSDT` (configurable)
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

### Confluence filters (default: Fib + MACD + ATR on; ADX off)

Signals only fire when the base setup **and** every enabled filter agree.

#### 1. Fibonacci confluence (`FILTER_FIB=1`)

Documented in `indicators.find_swing` / `fib_confluence` and applied in `engine._apply_confluence`:

1. Take the last `FIB_LOOKBACK` bars (default **80**, typical 50-100).
2. `swing_high` = max(high) in the window; `swing_low` = min(low).
3. **Upswing** if the low occurs *before* the high (prior up move).  
   **Downswing** if the high occurs *before* the low (prior down move).
4. Classic retracements **0.382 / 0.5 / 0.618**:
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

#### 4. Optional ADX (`FILTER_ADX=0` by default)

- Wilder ADX(14); only trade if `ADX >= ADX_MIN` (default **20**).
- Prefer Fib+MACD+ATR; enable ADX if you want a stronger trend gate.

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
  levels.py           # entries / TPs / SL
  engine.py           # direction + confluence + cooldown + scan
  backtest_core.py    # fill simulation helpers
  backtest.py         # historical walk-forward backtester
  telegram_client.py  # Bot API + dry-run
  runner.py           # CLI
tests/
  test_indicators.py
  test_levels.py
  test_engine_direction.py
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
# Default 15m (INTERVAL env / Config)
python -m signal_bot.backtest --days 120 --symbols BTCUSDT,ETHUSDT
# or:
python -m signal_bot --backtest --days 120 --symbols BTCUSDT,ETHUSDT

# Experimental 1h timeframe
python -m signal_bot.backtest --days 120 --symbols BTCUSDT,ETHUSDT --interval 1h
# equivalent:
INTERVAL=1h python -m signal_bot.backtest --days 120 --symbols BTCUSDT,ETHUSDT
python -m signal_bot --backtest --days 120 --symbols BTCUSDT,ETHUSDT --interval 1h
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

Same filters (Fib+MACD+ATR on, ADX off), ~120 days, BTCUSDT+ETHUSDT:

| TF | Trades | Win% | Total R | MaxDD R | PF | Notes |
|----|--------|------|---------|---------|----|-------|
| **15m** (default) | 124 | 44.4% | -2.23 | 14.55 | 0.95 | Primary / live default |
| **1h** (experimental) | 47 | 40.4% | -1.25 | 4.61 | 0.93 | Fewer trades, lower DD; not clearly better overall |

Re-run before changing the live default.

## Tests

```bash
pip install pytest
pytest -q
```

Tests cover indicators (incl. MACD/ATR/ADX/Fib), level generation, filter logic, and backtest simulation helpers **without network**.

## Configuration cheat sheet

| Variable | Default | Notes |
|----------|---------|-------|
| `SYMBOLS` | `BTCUSDT,ETHUSDT` | Comma-separated |
| `INTERVAL` | `15m` | Binance interval (`15m` live default; `1h` experimental via env/`--interval`) |
| `LEVERAGE` | `10` | Label only |
| `EMA_FAST` / `EMA_SLOW` | `9` / `21` | |
| `RSI_*` | `14` / `70` / `30` | |
| `FILTER_FIB` | `1` | Fib confluence |
| `FILTER_MACD` | `1` | MACD confirmation |
| `FILTER_ATR` | `1` | ATR% chop/extreme gate |
| `FILTER_ADX` | `0` | Optional ADX gate |
| `FIB_LOOKBACK` | `80` | Swing window (bars) |
| `FIB_TOL_PCT` / `FIB_TOL_ATR` | `0.25` / `0.5` | Proximity tolerance |
| `MACD_FAST/SLOW/SIGNAL` | `12/26/9` | |
| `ATR_PERIOD` / `ATR_MIN_PCT` / `ATR_MAX_PCT` | `14` / `0.15` / `0` | `0` max = off |
| `ADX_PERIOD` / `ADX_MIN` | `14` / `20` | Used only if `FILTER_ADX=1` |
| `ENTRY_OFFSETS_PCT` | `0,-0.3,-0.6,-1.0` | Exactly 4 |
| `TP_TARGETS_PCT` | `0.5,1.0,1.5,2.5,4.0` | Exactly 5 |
| `SL_BEYOND_LADDER_PCT` | `0.5` | Beyond farthest entry |
| `COOLDOWN_HOURS` | `5` | Per symbol/side |
| `DRY_RUN` | `1` | Forced if tokens missing |

### Toggling filters

```bash
# Baseline EMA+RSI only (previous behaviour)
FILTER_FIB=0 FILTER_MACD=0 FILTER_ATR=0 FILTER_ADX=0 python -m signal_bot.backtest --days 120

# Default confluence stack
FILTER_FIB=1 FILTER_MACD=1 FILTER_ATR=1 FILTER_ADX=0 python -m signal_bot.backtest --days 120

# Add ADX trend gate
FILTER_ADX=1 ADX_MIN=25 python -m signal_bot.backtest --days 120
```

## License

MIT
