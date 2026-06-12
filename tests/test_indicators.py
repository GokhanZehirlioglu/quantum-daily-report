"""Tests for core/indicators.py — SMA, MACD, RSI, ATR, compute_all."""

import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from core.indicators import sma, macd, rsi, atr, compute_all

# ─── Synthetic dataset ──────────────────────────────────────
np.random.seed(42)
dates = pd.date_range("2024-01-01", periods=260, freq="D")
close = 100 + np.cumsum(np.random.randn(260) * 0.5)
high = close + np.abs(np.random.randn(260)) * 1.5
low = close - np.abs(np.random.randn(260)) * 1.5
open_ = low + (high - low) * np.random.rand(260)
volume = np.random.randint(500_000, 5_000_000, 260)

df = pd.DataFrame({
    "open": open_, "high": high, "low": low,
    "close": close, "volume": volume,
}, index=dates)


def verify_all():
    errors = []

    # ── SMA ──
    s20 = sma(df["close"], 20)
    if len(s20.dropna()) == 0:
        errors.append("SMA(20) all NaN")
    expected_sma20_20 = df["close"].iloc[:20].mean()
    if not np.isclose(s20.iloc[19], expected_sma20_20):
        errors.append(f"SMA(20)[19]={s20.iloc[19]} != {expected_sma20_20}")
    # SMA equals rolling mean
    sma50 = sma(df["close"], 50)
    if not np.isclose(sma50.iloc[49], df["close"].iloc[:50].mean()):
        errors.append("SMA(50) mismatch")

    # ── MACD ──
    ml, ms, mh = macd(df["close"])
    if ml.isna().all():
        errors.append("MACD line all NaN")
    if mh.isna().all():
        errors.append("MACD hist all NaN")
    # MACD = EMA12 - EMA26
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    if not np.isclose(ml.iloc[-1], ema12.iloc[-1] - ema26.iloc[-1]):
        errors.append("MACD formula wrong")

    # ── RSI ──
    r = rsi(df["close"])
    if r.isna().all():
        errors.append("RSI all NaN")
    r_last = r.iloc[-1]
    if not (0 <= r_last <= 100):
        errors.append(f"RSI={r_last} outside [0, 100]")
    # All RSI values should be 0-100
    valid = r.dropna()
    if valid.min() < 0 or valid.max() > 100:
        errors.append("RSI exceeds [0, 100]")

    # ── ATR ──
    at = atr(df["high"], df["low"], df["close"])
    if at.isna().all():
        errors.append("ATR all NaN")
    if at.iloc[-1] <= 0:
        errors.append(f"ATR={at.iloc[-1]} must be > 0")
    # ATR(14) for volatile data should be reasonable
    if not (0.5 < at.iloc[-1] < 10):
        errors.append(f"ATR={at.iloc[-1]} outside expected range (0.5, 10)")

    # ── compute_all ──
    full = compute_all(df)
    expected_cols = ["sma_20", "sma_50", "sma_200", "macd", "macd_signal",
                     "macd_hist", "macd_bullish", "rsi", "atr"]
    for col in expected_cols:
        if col not in full.columns:
            errors.append(f"compute_all missing column: {col}")

    return errors


errors = verify_all()
print(f"Errors: {len(errors)}")
for e in errors:
    print(f"  FAIL: {e}")
if not errors:
    print("ALL indicator tests PASSED")
