"""
Technical indicators — pure NumPy/Pandas, zero external TA dependencies.

All functions accept a ``pd.DataFrame`` with columns ``open``, ``high``,
``low``, ``close``, ``volume`` (all lowercase) — the standard ``DailyData``
format established in Sprint 1.

Exposed:
    - sma(series, period)         → Simple Moving Average
    - macd(close, fast, slow, signal) → MACD line, signal line, histogram
    - rsi(close, period)          → Relative Strength Index
    - atr(high, low, close, period) → Average True Range
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd


# ─── SMA ─────────────────────────────────────────────────────

def sma(series: pd.Series, period: int) -> pd.Series:
    """
    Simple Moving Average.

    Args:
        series: Price series (typically ``close``).
        period: Look-back window.

    Returns:
        ``pd.Series`` of SMA values. Leading values are ``NaN`` until
        at least *period* data points are available.
    """
    return series.rolling(window=period, min_periods=period).mean()


# ─── MACD ───────────────────────────────────────────────────

def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    MACD (Moving Average Convergence Divergence).

    Args:
        close: Closing price series.
        fast: Fast EMA period (default 12).
        slow: Slow EMA period (default 26).
        signal: Signal line period (default 9).

    Returns:
        ``(macd_line, signal_line, histogram)`` as ``pd.Series``.
        *histogram* = *macd_line* − *signal_line*.
    """
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


# ─── RSI ─────────────────────────────────────────────────────

def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """
    Relative Strength Index (Wilder's smoothed version).

    Args:
        close: Closing price series.
        period: Look-back window (default 14).

    Returns:
        ``pd.Series`` of RSI values (0–100). ``NaN`` until at least
        *period* data points are available.
    """
    delta = close.diff()

    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    # Wilder's smoothing — first value is SMA, then EMA
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


# ─── ATR ─────────────────────────────────────────────────────

def atr(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 14,
) -> pd.Series:
    """
    Average True Range (Wilder's smoothed).

    Args:
        high: High price series.
        low: Low price series.
        close: Close price series.
        period: Look-back window (default 14).

    Returns:
        ``pd.Series`` of ATR values.
    """
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder's smoothing
    return tr.ewm(alpha=1.0 / period, adjust=False).mean()


# ─── BATCH INDICATORS (convenience) ────────────────────────

def compute_all(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute SMA(20), SMA(50), SMA(200), MACD, RSI(14), and ATR(14)
    on *df* and append columns.

    Args:
        df: Must contain columns ``open, high, low, close, volume``.

    Returns:
        A new ``pd.DataFrame`` with indicator columns added.
    """
    result = df.copy()
    c, h, l = result["close"], result["high"], result["low"]

    # SMAs
    result["sma_20"] = sma(c, 20)
    result["sma_50"] = sma(c, 50)
    result["sma_200"] = sma(c, 200)

    # MACD
    macd_line, macd_signal, macd_hist = macd(c)
    result["macd"] = macd_line
    result["macd_signal"] = macd_signal
    result["macd_hist"] = macd_hist
    result["macd_bullish"] = macd_line > macd_signal

    # RSI
    result["rsi"] = rsi(c)

    # ATR
    result["atr"] = atr(h, l, c)

    return result
