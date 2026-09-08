# Telegram Crypto Signal Bot

Educational / informational trade-**signal** bot for Telegram. It reads **public** Binance USDT-M futures klines (no API keys, **no live trading**), applies EMA + RSI on 15m candles with **Fib / MACD / ATR / HTF bias / Supertrend** confluence (volume/SMC/ADX kept in code but **off by default**), and posts LONG/SHORT signals with a 4-entry ladder, 5 take-profits, and 1 stop-loss.

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

### Confluence filters (default: Fib + MACD + ATR + HTF + Supertrend; Vol/SMC/ADX off)

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

#### 5. Higher-timeframe trend bias (`FILTER_HTF=1` by default)

**Honest note:** indicators alone often do not create a durable edge. HTF bias is a simple regime filter — trade **with** the 4h trend, skip when it disagrees.

1. Build / fetch **4h** candles (`HTF_INTERVAL=4h`; backtest resamples from 15m; live fetches 4h klines).
2. Compute EMA fast / slow on completed 4h closes only (no forming-candle lookahead). Defaults: **EMA20 / EMA50**.
3. **LONG:** require `EMA20 > EMA50` on 4h. **SHORT:** require `EMA20 < EMA50`.
4. If HTF disagrees → **skip**.

#### 6. Supertrend filter (`FILTER_SUPERTREND=1` by default)

ATR-based Supertrend on the signal timeframe (`SUPERTREND_PERIOD=10`, `SUPERTREND_MULTIPLIER=3` — common defaults; configurable).

- **LONG** only if Supertrend direction is bullish (price effectively above the ST line).
- **SHORT** only if bearish (price below ST).
- Disagreement → **skip**.

#### 7. Volume filters (`FILTER_VOLUME=0`, `FILTER_OBV=0` by default — kept, off)

Prior ~120d multi-coin backtest with Volume+SMC **worsened** expectancy vs Fib+MACD+ATR alone. Code remains in `signal_bot/volume.py`; enable via env if you want to re-test.

1. **Relative volume** (`FILTER_VOLUME`): `vol_ratio = volume / SMA(volume, VOL_SMA_PERIOD)` (default SMA **20**).
   Require `vol_ratio >= VOL_RATIO_MIN` (default **1.2**) on the signal bar, or the max over the last `VOL_CONFIRM_BARS` bars (default **1**).
2. **OBV / volume-price agreement** (`FILTER_OBV`): On-Balance Volume slope over `OBV_LOOKBACK` (default **5**).

#### 8. SMC approximations (`FILTER_SMC=0` by default — kept, off)

**Not a TradingView SMC clone.** Practical definitions in `signal_bot/smc.py` (BOS + FVG; optional OB). Off by default after the Volume+SMC stack underperformed the Fib+MACD+ATR baseline.

### Signal format (unchanged)

Still **4 entries / 5 TPs / 10x** leverage label + 1 SL beyond the ladder.

## Project layout

```
signal_bot/
  config.py / config_env.py
  htf_supertrend.py / engine_confluence.py
  engine.py / backtest.py / backtest_run.py / backtest_cli.py
  indicators.py / volume.py / smc.py / intervals.py
tests/
  test_htf_supertrend.py / test_engine_*.py / ...
.env.example
BACKTEST_RESULTS.md
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

See [BACKTEST_RESULTS.md](BACKTEST_RESULTS.md) for ~120d metrics and honesty notes.
