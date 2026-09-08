# Telegram Crypto Signal Bot

Educational / informational trade-**signal** bot for Telegram. It reads **public** Binance USDT-M futures klines (no API keys, **no live trading**), applies EMA + RSI on 15m candles, and posts LONG/SHORT signals with a 4-entry ladder, 5 take-profits, and 1 stop-loss.

> **Disclaimer:** This is not financial advice. Signals are for research/demo only. You are responsible for any trading decisions.

## Features

- Symbols: `BTCUSDT`, `ETHUSDT` (configurable)
- Leverage label: **10x** (configurable; informational only — bot does not place orders)
- Direction on **15m** candles:
  - **LONG** when fast EMA > slow EMA and RSI is not overbought (`< 70`)
  - **SHORT** when fast EMA < slow EMA and RSI is not oversold (`> 30`)
  - Mixed/choppy or filtered setups are **skipped** and logged
- 4 configurable entry % offsets, 5 TP % targets, SL beyond the ladder
- Per-symbol/side cooldown (~5h default) to reduce spam
- Telegram Bot API → channel; **dry-run** prints to stdout when `DRY_RUN=1` or tokens are missing

## Project layout

```
signal_bot/
  __init__.py
  __main__.py
  config.py           # env-based settings
  models.py           # Signal dataclass + message format
  binance_client.py   # public klines client
  indicators.py       # EMA + RSI
  levels.py           # entries / TPs / SL
  engine.py           # direction + cooldown + scan
  telegram_client.py  # Bot API + dry-run
  runner.py           # CLI
tests/
  test_indicators.py
  test_levels.py
  test_engine_direction.py
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
3. Copy the **bot token** → `TELEGRAM_BOT_TOKEN`

### 3. Channel admin

1. Create a public or private channel
2. Add your bot as an **administrator** with permission to post messages
3. Get the channel id:
   - Public: `@your_channel_username`
   - Private: forward a channel message to a bot like `@userinfobot`, or use the numeric id (often `-100…`)
4. Set `TELEGRAM_CHANNEL_ID`

### 4. Environment

```bash
cp .env.example .env
# Edit .env — for dry-run leave tokens empty and DRY_RUN=1
```

## Dry-run (recommended first)

```bash
export DRY_RUN=1
# or leave TELEGRAM_* unset
python -m signal_bot --once
```

Example stdout:

```
========== DRY RUN (Telegram) ==========
🔔 LONG Signal — BTCUSDT
Leverage: 10x
Ref price: 65000.0000

Entries:
  Entry 1: 65000.0000
  Entry 2: 64805.0000
  ...
Take profits:
  TP1: 65325.0000
  ...
Stop loss: 64252.xxx
Rationale: EMA9>EMA21 (bullish) and RSI=55.2<70
Time: 2026-09-08 03:00:00 UTC
========================================
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

## Tests

```bash
pip install pytest
pytest -q
```

Tests cover indicators and level generation **without network**.

## Configuration cheat sheet

| Variable | Default | Notes |
|----------|---------|-------|
| `SYMBOLS` | `BTCUSDT,ETHUSDT` | Comma-separated |
| `INTERVAL` | `15m` | Binance interval |
| `LEVERAGE` | `10` | Label only |
| `EMA_FAST` / `EMA_SLOW` | `9` / `21` | |
| `RSI_*` | `14` / `70` / `30` | |
| `ENTRY_OFFSETS_PCT` | `0,-0.3,-0.6,-1.0` | Exactly 4 |
| `TP_TARGETS_PCT` | `0.5,1.0,1.5,2.5,4.0` | Exactly 5 |
| `SL_BEYOND_LADDER_PCT` | `0.5` | Beyond farthest entry |
| `COOLDOWN_HOURS` | `5` | Per symbol/side |
| `DRY_RUN` | `1` | Forced if tokens missing |

## License

MIT
