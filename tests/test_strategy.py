"""Run with: python -m pytest -q"""
import numpy as np
import pandas as pd

from orb_bot.strategy import compute_signals


def synthetic(n=3000, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="1min")
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.001, n)))
    open_ = np.r_[close[0], close[:-1]]
    high = np.maximum(open_, close) * (1 + rng.uniform(0, 0.0008, n))
    low = np.minimum(open_, close) * (1 - rng.uniform(0, 0.0008, n))
    vol = rng.uniform(50, 150, n)
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": vol}, index=idx)


def test_no_lookahead():
    """Signals at time t must be identical whether or not later candles exist."""
    df = synthetic()
    full = compute_signals(df)
    for cut in (900, 1500, 2222, 2999):
        part = compute_signals(df.iloc[:cut])
        t = part.index[-1]
        for col in ("score_long", "score_short", "direction", "atr"):
            a, b = full.at[t, col], part.at[t, col]
            assert (a == b) or (pd.isna(a) and pd.isna(b)) or np.isclose(a, b), (col, cut)


def test_scores_in_range():
    sig = compute_signals(synthetic())
    assert sig["score"].between(0, 12).all()
    assert set(sig["direction"]) <= {"long", "short", "none"}
    assert (sig.loc[sig["score"] > 0, "score"] >= 3).all()  # a breakout is mandatory
