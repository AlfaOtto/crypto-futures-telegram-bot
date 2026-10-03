"""
Opening-range breakout (ORB) signal with a confluence score from 0 to 10.

Signals are computed on closed 1-minute candles. 5-minute indicators are
labelled at the CLOSE of their candle, so a 1-minute bar never sees a
5-minute candle that has not finished yet (no look-ahead).

Score (long side; the short side is symmetric):
  +3  close crosses an opening range (Asia 00:00, London 08:00, New York 13:00 UTC)
      or the 20-bar Donchian channel                    (mandatory)
  +2  relative volume > 1.5
  +2  strong bullish body (> 60 % of the range)
  +1  close above session VWAP
  +1  EMA 9 > EMA 21
  +1  EMA 21 > EMA 50
  +1  RSI between 50 and 70
  +1  ATR above its 50-bar average
(Maximum 12; the bot uses a configurable threshold, 10 by default.)
"""
import numpy as np
import pandas as pd

SESSIONS = {"asia": 0, "london": 8, "ny": 13}
SESSION_END = {"asia": 8, "london": 13, "ny": 21}


def atr(df, period=14):
    prev = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def rsi(close, period=14):
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    return 100 - 100 / (1 + gain / loss.replace(0, np.nan))


def ema(s, period):
    return s.ewm(span=period, adjust=False).mean()


def session_vwap(df):
    typical = (df["high"] + df["low"] + df["close"]) / 3
    day = df.index.date
    pv = (typical * df["volume"]).groupby(day).cumsum()
    vol = df["volume"].groupby(day).cumsum()
    return pv / vol.replace(0, np.nan)


def opening_ranges(df, minutes=30):
    """High/low of the first `minutes` of each session, usable only after the range is complete."""
    out = pd.DataFrame(index=df.index)
    hour, minute, day = df.index.hour, df.index.minute, pd.Series(df.index.date, index=df.index)
    for name, start in SESSIONS.items():
        in_range = (hour == start) & (minute < minutes)
        rng = df[in_range].groupby(day[in_range])
        out[name + "_high"] = day.map(rng["high"].max())
        out[name + "_low"] = day.map(rng["low"].min())
        after = ((hour == start) & (minute >= minutes)) | ((hour > start) & (hour < SESSION_END[name]))
        out[name + "_window"] = after
    return out


def compute_signals(df):
    """df: 1-minute OHLCV indexed by naive UTC timestamps (closed candles only)."""
    if df is None or df.empty:
        return df
    df = df.copy()
    m5 = df.resample("5min", label="right", closed="left").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    m5["ema9"], m5["ema21"], m5["ema50"] = ema(m5["close"], 9), ema(m5["close"], 21), ema(m5["close"], 50)
    m5["atr"] = atr(m5)
    m5["rsi"] = rsi(m5["close"])
    m5["rvol"] = m5["volume"] / m5["volume"].rolling(20).mean().replace(0, np.nan)
    m5["don_hi"] = m5["high"].rolling(20).max()
    m5["don_lo"] = m5["low"].rolling(20).min()
    m5["body_pct"] = (m5["close"] - m5["open"]).abs() / (m5["high"] - m5["low"]).replace(0, np.nan)
    m5["bullish"] = m5["close"] > m5["open"]
    for col in ["ema9", "ema21", "ema50", "atr", "rsi", "rvol", "don_hi", "don_lo", "body_pct", "bullish"]:
        df[col] = m5[col].reindex(df.index, method="ffill")
    df["bullish"] = df["bullish"].astype("boolean").fillna(False).astype(bool)
    df["vwap"] = session_vwap(df)
    df = df.join(opening_ranges(df))

    prev = df["close"].shift(1)
    up = pd.Series(False, index=df.index)
    dn = pd.Series(False, index=df.index)
    for name in SESSIONS:
        w, hi, lo = df[name + "_window"], df[name + "_high"], df[name + "_low"]
        up |= (w & (prev <= hi) & (df["close"] > hi)).fillna(False)
        dn |= (w & (prev >= lo) & (df["close"] < lo)).fillna(False)
    dhi, dlo = df["don_hi"].shift(1), df["don_lo"].shift(1)
    up |= ((prev <= dhi) & (df["close"] > dhi)).fillna(False)
    dn |= ((prev >= dlo) & (df["close"] < dlo)).fillna(False)

    atr_avg = df["atr"].rolling(50).mean()

    def score(brk, strong_body, vwap_ok, e1, e2, rsi_ok):
        parts = [brk * 3, (brk & (df["rvol"] > 1.5)) * 2, (brk & strong_body) * 2,
                 brk & vwap_ok, brk & e1, brk & e2, brk & rsi_ok, brk & (df["atr"] > atr_avg)]
        return sum(p.fillna(False).astype(int) for p in parts)

    strong = df["body_pct"] > 0.6
    df["score_long"] = score(up, strong & df["bullish"], df["close"] > df["vwap"],
                             df["ema9"] > df["ema21"], df["ema21"] > df["ema50"], df["rsi"].between(50, 70))
    df["score_short"] = score(dn, strong & ~df["bullish"], df["close"] < df["vwap"],
                              df["ema9"] < df["ema21"], df["ema21"] < df["ema50"], df["rsi"].between(30, 50))
    df["score"] = df[["score_long", "score_short"]].max(axis=1)
    df["direction"] = np.where(df["score_long"] > df["score_short"], "long",
                               np.where(df["score_short"] > df["score_long"], "short", "none"))
    return df
