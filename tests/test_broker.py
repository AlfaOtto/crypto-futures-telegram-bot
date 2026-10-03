from orb_bot.broker import PaperBroker
from orb_bot.config import Settings


def make(**kw):
    s = Settings()
    s.initial_capital, s.risk_per_trade, s.leverage = 1000.0, 0.01, 10
    s.maker_fee = s.taker_fee = s.stop_slippage = s.funding_per_8h = 0.0
    s.reports_dir = "/tmp/orb_test_reports"
    for k, v in kw.items():
        setattr(s, k, v)
    return PaperBroker(s)


def test_limit_needs_trade_through():
    b = make()
    b.place("ETH/USDT", "long", 100.0, 1.0)
    b.on_candle("ETH/USDT", 101, 100.0)  # touch only
    assert not b.positions["ETH/USDT"].filled
    b.on_candle("ETH/USDT", 101, 99.9)
    assert b.positions["ETH/USDT"].filled


def test_stop_loses_one_R():
    b = make(partial_at_r=0)
    b.place("ETH/USDT", "long", 100.0, 1.0)      # stop 1 %, risk 10 USDT
    b.on_candle("ETH/USDT", 100.5, 99.9)
    b.on_candle("ETH/USDT", 100.5, 98.0)
    assert b.trades[-1]["reason"] == "stop"
    assert abs(b.trades[-1]["R"] + 1) < 1e-9
    assert abs(b.capital - 990) < 1e-6


def test_stop_first_when_both_hit():
    b = make(partial_at_r=0)
    b.place("SOL/USDT", "short", 100.0, 1.0)
    b.on_candle("SOL/USDT", 100.1, 99.5)
    b.on_candle("SOL/USDT", 102.0, 97.0)          # stop and target in one candle
    assert b.trades[-1]["reason"] == "stop"


def test_partial_then_breakeven():
    b = make(partial_at_r=1.0, reward_risk=2.0)
    b.place("BNB/USDT", "long", 100.0, 1.0)
    b.on_candle("BNB/USDT", 100.2, 99.9)
    b.on_candle("BNB/USDT", 101.2, 100.1)         # partial at +1R
    b.on_candle("BNB/USDT", 100.5, 99.5)          # back to entry -> break-even
    t = b.trades[-1]
    assert t["reason"] == "breakeven" and abs(t["R"] - 0.5) < 1e-9


def test_drawdown_halts_new_orders():
    b = make(max_drawdown=0.02, partial_at_r=0)
    for sym in ("A", "B", "C"):
        b.place(sym, "long", 100.0, 1.0)
        b.on_candle(sym, 100.5, 99.9)
        b.on_candle(sym, 100.5, 98.0)
    assert b.halted() and b.place("D", "long", 100.0, 1.0) is None
