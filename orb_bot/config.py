"""
Configuration, read from environment variables (.env).

Every value has a conservative default so the bot can start in paper mode
without any configuration except, optionally, the Telegram credentials.
"""
import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _f(name, default):
    return float(os.getenv(name, default))


def _i(name, default):
    return int(os.getenv(name, default))


def _list(name, default):
    return [s.strip() for s in os.getenv(name, default).split(",") if s.strip()]


@dataclass
class Settings:
    # Telegram
    telegram_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    # Market
    exchange: str = field(default_factory=lambda: os.getenv("EXCHANGE", "binanceusdm"))
    symbols: List[str] = field(default_factory=lambda: _list(
        "SYMBOLS", "ETH/USDT,SOL/USDT,BNB/USDT,ADA/USDT,AVAX/USDT,LINK/USDT"))
    timeframe: str = "1m"
    candles: int = field(default_factory=lambda: _i("CANDLES", 1500))
    loop_seconds: int = field(default_factory=lambda: _i("LOOP_SECONDS", 60))

    # Strategy
    min_score: int = field(default_factory=lambda: _i("MIN_SCORE", 10))
    atr_stop: float = field(default_factory=lambda: _f("ATR_STOP", 1.0))
    reward_risk: float = field(default_factory=lambda: _f("REWARD_RISK", 1.5))
    partial_at_r: float = field(default_factory=lambda: _f("PARTIAL_AT_R", 1.0))
    limit_expiry_bars: int = field(default_factory=lambda: _i("LIMIT_EXPIRY_BARS", 5))

    # Risk
    initial_capital: float = field(default_factory=lambda: _f("INITIAL_CAPITAL", 1000))
    risk_per_trade: float = field(default_factory=lambda: _f("RISK_PER_TRADE", 0.01))
    leverage: float = field(default_factory=lambda: _f("LEVERAGE", 10))
    max_positions: int = field(default_factory=lambda: _i("MAX_POSITIONS", 4))
    max_drawdown: float = field(default_factory=lambda: _f("MAX_DRAWDOWN", 0.25))

    # Costs
    maker_fee: float = field(default_factory=lambda: _f("MAKER_FEE", 0.0002))
    taker_fee: float = field(default_factory=lambda: _f("TAKER_FEE", 0.0005))
    stop_slippage: float = field(default_factory=lambda: _f("STOP_SLIPPAGE", 0.0003))
    funding_per_8h: float = field(default_factory=lambda: _f("FUNDING_PER_8H", 0.0001))

    reports_dir: str = field(default_factory=lambda: os.getenv("REPORTS_DIR", "reports"))
