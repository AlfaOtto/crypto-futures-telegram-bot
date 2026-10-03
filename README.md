# Crypto Futures Telegram Bot

**A 24/7 paper-trading bot for crypto perpetual futures, monitored and controlled from Telegram.**

It scans several pairs every minute, scores opening-range breakouts, simulates limit entries with stop-loss, take-profit, partial exit and break-even, and reports every event to your phone. Market data comes from public exchange endpoints through [ccxt](https://github.com/ccxt/ccxt), so no exchange API key is needed.

## Features

- **Multi-pair scanner** on closed 1-minute candles, any exchange supported by ccxt
- **Opening-range breakout signal** (Asia, London, New York sessions + Donchian channel) with a 0-12 confluence score: volume, candle body, VWAP, EMA trend, RSI, volatility
- **No look-ahead**: 5-minute indicators are only used once their candle has closed; a unit test checks that signals never change when future candles are added
- **Realistic paper broker**: limit orders fill only if price trades through, stop assumed first when stop and target share a candle, maker/taker fees, stop slippage, funding, liquidation price
- **Risk controls**: fixed % risk per trade, leverage cap, free-margin check, max open positions, max-drawdown kill switch
- **Secure Telegram control**: commands are accepted only from your own chat ID
- **CSV trade log** and a systemd unit for VPS deployment

## Telegram commands

| Command | Reply |
|---|---|
| `/status` | Running or paused, capital, drawdown, open and pending positions |
| `/stats` | Number of trades, win rate, profit factor, average R |
| `/trades` | Last 10 closed trades |
| `/config` | Pairs and strategy parameters |
| `/pause` / `/resume` | Stop or restart new entries (open positions keep being managed) |
| `/stop` | Shut the bot down cleanly |

Every entry, partial exit and close is also pushed automatically.

## Project layout

```
bot.py                 main loop and Telegram commands
orb_bot/config.py      settings from .env with safe defaults
orb_bot/strategy.py    indicators and breakout score
orb_bot/broker.py      paper broker (fills, exits, fees, risk)
orb_bot/telegram.py    Telegram long polling with chat-ID authorization
tests/                 look-ahead test and broker tests
deploy/orb-bot.service systemd unit for a VPS
```

## Quick start

```bash
git clone https://github.com/AlfaOtto/crypto-futures-telegram-bot.git
cd crypto-futures-telegram-bot
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your Telegram token and chat ID
python -m pytest -q           # 7 tests
python bot.py
```

Create the Telegram bot with [@BotFather](https://t.me/BotFather) and get your chat ID from [@userinfobot](https://t.me/userinfobot).

## About performance

This repository is an execution and monitoring framework. The bundled breakout signal is an example: it has **not** shown a statistically proven edge, and no strategy should trade real money before passing an out-of-sample test with costs and placebo checks. I use [crypto-backtest-validator](https://github.com/AlfaOtto/crypto-backtest-validator) for that step.

## Services

I build custom trading bots (Binance, Bybit, MEXC, Hyperliquid), Telegram bots and Python automations, deployed 24/7 on a VPS. Contact me on Upwork.
