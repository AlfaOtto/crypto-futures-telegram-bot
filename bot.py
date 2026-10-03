"""
bot.py - run the ORB paper-trading bot.

    python bot.py            # loop forever, one cycle per minute
    python bot.py --once     # single cycle (useful for cron or a quick check)

Market data comes from the exchange's public endpoints through ccxt:
no API key is needed in paper mode.
"""
import argparse
import logging
import signal
import sys
import time
from datetime import datetime

import ccxt
import pandas as pd

from orb_bot.broker import PaperBroker
from orb_bot.config import Settings
from orb_bot.strategy import compute_signals
from orb_bot.telegram import Telegram

log = logging.getLogger("orb_bot")


def fetch_closed_candles(exchange, symbol, settings):
    raw = exchange.fetch_ohlcv(symbol, settings.timeframe, limit=settings.candles)
    df = pd.DataFrame(raw, columns=["ts", "open", "high", "low", "close", "volume"])
    df.index = pd.to_datetime(df.pop("ts"), unit="ms")
    return df.iloc[:-1]  # drop the candle that is still forming


class Bot:
    def __init__(self, settings):
        self.s = settings
        self.tg = Telegram(settings.telegram_token, settings.telegram_chat_id)
        self.broker = PaperBroker(settings, notify=self.tg.send)
        self.exchange = getattr(ccxt, settings.exchange)({"enableRateLimit": True})
        self.paused = False
        self.running = True
        self.started = datetime.utcnow()
        self.last_bar = {}
        self._register_commands()

    def _register_commands(self):
        tg, b = self.tg, self.broker

        @tg.command("status")
        def status():
            lines = ["{} | capital {:.2f} USDT | drawdown {:.1f}%".format(
                "PAUSED" if self.paused else "RUNNING", b.capital, 100 * b.drawdown),
                "uptime " + str(datetime.utcnow() - self.started).split(".")[0]]
            for p in b.positions.values():
                lines.append("{} {} @ {:.4f}{}".format(
                    p.symbol, p.side, p.entry, "" if p.filled else " (pending)"))
            return "\n".join(lines)

        @tg.command("stats")
        def stats():
            st = b.summary()
            return "trades {} | win rate {:.0%} | PF {:.2f} | avg {:+.2f}R".format(
                st["trades"], st["win_rate"], st["profit_factor"], st["avg_R"])

        @tg.command("trades")
        def trades():
            last = b.trades[-10:]
            if not last:
                return "No closed trades yet."
            return "\n".join("{time} {symbol} {side} {reason} {pnl:+.2f} ({R:+.2f}R)".format(**t) for t in last)

        @tg.command("config")
        def config():
            s = self.s
            return "symbols {}\nscore >= {} | stop {} ATR | RR {} | risk {:.1%} | leverage {:.0f}x".format(
                ", ".join(s.symbols), s.min_score, s.atr_stop, s.reward_risk, s.risk_per_trade, s.leverage)

        @tg.command("pause")
        def pause():
            self.paused = True
            return "Paused: no new entries, open positions still managed."

        @tg.command("resume")
        def resume():
            self.paused = False
            return "Resumed."

        @tg.command("stop")
        def stop():
            self.running = False
            return "Stopping after the current cycle."

    def cycle(self):
        for symbol in self.s.symbols:
            try:
                df = fetch_closed_candles(self.exchange, symbol, self.s)
            except ccxt.BaseError as exc:
                log.warning("%s: data error %s", symbol, exc)
                continue
            if len(df) < 300:
                continue
            bar_time = df.index[-1]
            if self.last_bar.get(symbol) == bar_time:
                continue
            new = df[df.index > self.last_bar[symbol]] if symbol in self.last_bar else df.iloc[-1:]
            for _, bar in new.iterrows():  # replay every candle missed since the last cycle
                self.broker.on_candle(symbol, bar["high"], bar["low"])
            self.last_bar[symbol] = bar_time
            sig = compute_signals(df).iloc[-1]
            if (not self.paused and sig["direction"] != "none" and sig["score"] >= self.s.min_score
                    and symbol not in self.broker.positions):
                self.broker.place(symbol, sig["direction"], sig["close"], sig["atr"])
        if self.broker.halted():
            self.paused = True
            self.tg.send("Max drawdown reached: new entries disabled.")

    def run(self, once=False):
        self.tg.start()
        self.tg.send("ORB paper bot started on {} symbols. Send /status".format(len(self.s.symbols)))
        while self.running:
            started = time.time()
            self.cycle()
            log.info("capital %.2f | open %d | trades %d", self.broker.capital,
                     len(self.broker.positions), len(self.broker.trades))
            if once:
                break
            time.sleep(max(1, self.s.loop_seconds - (time.time() - started)))
        self.tg.send("Bot stopped. Final capital {:.2f} USDT".format(self.broker.capital))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--once", action="store_true", help="run a single cycle and exit")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    bot = Bot(Settings())
    signal.signal(signal.SIGTERM, lambda *_: setattr(bot, "running", False))
    try:
        bot.run(once=args.once)
    except KeyboardInterrupt:
        bot.tg.send("Bot stopped manually.")
        sys.exit(0)


if __name__ == "__main__":
    main()
