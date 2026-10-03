"""
Paper broker: simulates limit entries, stop-loss, take-profit, partial exit,
break-even, liquidation, fees and funding on closed candles.

Conservative conventions:
  - a limit entry fills only if price trades THROUGH the limit (not just touches it)
  - if stop and target are both inside the same candle, the stop is assumed first
  - stops are taker orders with slippage; entries and targets are maker orders
"""
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    side: str
    entry: float
    stop: float
    target: float
    partial: Optional[float]
    liquidation: float
    notional: float
    margin: float
    risk_usd: float
    bars_left: int
    filled: bool = False
    remaining: float = 1.0
    realized: float = 0.0
    breakeven: bool = False
    bars_open: int = 0


@dataclass
class PaperBroker:
    settings: object
    notify: Callable[[str], None] = lambda text: None
    capital: float = field(init=False)
    peak: float = field(init=False)
    positions: Dict[str, Position] = field(default_factory=dict)
    trades: List[dict] = field(default_factory=list)

    def __post_init__(self):
        self.capital = self.peak = self.settings.initial_capital

    # ---------- account state ----------
    @property
    def margin_used(self):
        return sum(p.margin * p.remaining for p in self.positions.values())

    @property
    def drawdown(self):
        return (self.peak - self.capital) / self.peak if self.peak > 0 else 0.0

    def halted(self):
        return self.drawdown >= self.settings.max_drawdown

    # ---------- orders ----------
    def place(self, symbol, side, price, atr_value):
        s = self.settings
        if self.halted() or symbol in self.positions or len(self.positions) >= s.max_positions:
            return None
        if not atr_value or atr_value <= 0 or pd.isna(atr_value):
            return None
        stop_pct = atr_value * s.atr_stop / price
        if not 0.0005 <= stop_pct <= 0.05:
            return None
        if stop_pct >= 0.9 / s.leverage:
            log.info("%s skipped: stop beyond liquidation at %.0fx", symbol, s.leverage)
            return None
        risk_usd = self.capital * s.risk_per_trade
        notional = risk_usd / stop_pct
        margin = notional / s.leverage
        if margin > self.capital - self.margin_used:
            log.info("%s skipped: not enough free margin", symbol)
            return None
        sign = 1 if side == "long" else -1
        pos = Position(
            symbol=symbol, side=side, entry=price,
            stop=price * (1 - sign * stop_pct),
            target=price * (1 + sign * stop_pct * s.reward_risk),
            partial=price * (1 + sign * stop_pct * s.partial_at_r) if 0 < s.partial_at_r < s.reward_risk else None,
            liquidation=price * (1 - sign * 0.9 / s.leverage),
            notional=notional, margin=margin, risk_usd=risk_usd, bars_left=s.limit_expiry_bars)
        self.positions[symbol] = pos
        log.info("%s %s limit @ %.4f (stop %.4f, target %.4f)", symbol, side, price, pos.stop, pos.target)
        return pos

    # ---------- candle update ----------
    def on_candle(self, symbol, high, low):
        pos = self.positions.get(symbol)
        if pos is None:
            return
        long = pos.side == "long"
        if not pos.filled:
            through = low < pos.entry if long else high > pos.entry
            if through:
                pos.filled = True
                self._fee(pos.notional, self.settings.maker_fee)
                self.notify("ENTRY {} {} @ {:.4f}\nstop {:.4f} | target {:.4f}".format(
                    symbol, pos.side.upper(), pos.entry, pos.stop, pos.target))
                return  # managed from the next candle (fill time inside the bar is unknown)
            pos.bars_left -= 1
            if pos.bars_left <= 0:
                del self.positions[symbol]
            return

        pos.bars_open += 1
        if pos.bars_open % 480 == 0:  # funding every 8 hours of 1-minute bars
            self._fee(pos.notional * pos.remaining, self.settings.funding_per_8h)

        if (low <= pos.liquidation) if long else (high >= pos.liquidation):
            return self._close(pos, pos.liquidation, "liquidation")
        if (low <= pos.stop) if long else (high >= pos.stop):
            slip = self.settings.stop_slippage
            px = pos.stop * (1 - slip) if long else pos.stop * (1 + slip)
            return self._close(pos, px, "breakeven" if pos.breakeven else "stop", taker=True)
        if pos.partial and not pos.breakeven and ((high >= pos.partial) if long else (low <= pos.partial)):
            pnl = self._pnl(pos, pos.partial, 0.5)
            self._fee(pos.notional * 0.5, self.settings.maker_fee)
            self.capital += pnl
            pos.realized += pnl
            pos.remaining = 0.5
            pos.breakeven = True
            pos.stop = pos.entry
            self.notify("PARTIAL {} +{:.2f} USDT, stop moved to break-even".format(symbol, pnl))
        if (high >= pos.target) if long else (low <= pos.target):
            return self._close(pos, pos.target, "target")

    # ---------- helpers ----------
    def _pnl(self, pos, price, fraction):
        move = (price - pos.entry) / pos.entry
        if pos.side == "short":
            move = -move
        return move * pos.notional * fraction

    def _fee(self, notional, rate):
        self.capital -= notional * rate

    def _close(self, pos, price, reason, taker=False):
        if reason == "liquidation":
            pnl = -pos.margin * pos.remaining
        else:
            pnl = self._pnl(pos, price, pos.remaining)
            self._fee(pos.notional * pos.remaining, self.settings.taker_fee if taker else self.settings.maker_fee)
        self.capital += pnl
        self.peak = max(self.peak, self.capital)
        total = pos.realized + pnl
        trade = {"time": datetime.utcnow().strftime("%Y-%m-%d %H:%M"), "symbol": pos.symbol, "side": pos.side,
                 "entry": round(pos.entry, 6), "exit": round(price, 6), "reason": reason,
                 "pnl": round(total, 4), "R": round(total / pos.risk_usd, 3), "capital": round(self.capital, 2)}
        self.trades.append(trade)
        del self.positions[pos.symbol]
        self.notify("{} {} {}: {:+.2f} USDT ({:+.2f}R)\ncapital {:.2f}".format(
            reason.upper(), pos.symbol, pos.side.upper(), total, trade["R"], self.capital))
        os.makedirs(self.settings.reports_dir, exist_ok=True)
        pd.DataFrame(self.trades).to_csv(os.path.join(self.settings.reports_dir, "paper_trades.csv"), index=False)

    # ---------- reporting ----------
    def summary(self):
        df = pd.DataFrame(self.trades)
        n = len(df)
        if n == 0:
            return {"trades": 0, "win_rate": 0.0, "profit_factor": 0.0, "avg_R": 0.0}
        gains = df.loc[df["pnl"] > 0, "pnl"].sum()
        losses = -df.loc[df["pnl"] < 0, "pnl"].sum()
        return {"trades": n, "win_rate": float((df["pnl"] > 0).mean()),
                "profit_factor": float(gains / losses) if losses > 0 else float("inf"),
                "avg_R": float(df["R"].mean())}
