"""Tests for core/gap_risk.py — calculate_g_worst."""

import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import numpy as np
from core.gap_risk import calculate_g_worst


def verify_all():
    errors = []

    # ── Test 1: Known gap ──
    # Close[0]=100, Open[1]=90 → -10% → g_worst=0.10
    df = pd.DataFrame({
        "open": [101, 90, 105, 100, 102],
        "close": [100, 95, 104, 101, 103],
    })
    g = calculate_g_worst(df)
    expected = abs((90 - 100) / 100)  # = 0.10
    if not math.isclose(g, expected, rel_tol=1e-5):
        errors.append(f"Test 1: got {g}, expected {expected}")

    # ── Test 2: Larger gap ──
    df2 = pd.DataFrame({
        "open": [100, 100, 80, 101, 99],
        "close": [100, 95, 90, 100, 98],
    })
    g2 = calculate_g_worst(df2)
    # Open[2]=80, Close[1]=95 → (80-95)/95 = -0.15789
    expected2 = abs((80 - 95) / 95)
    if not math.isclose(g2, expected2, rel_tol=1e-4):
        errors.append(f"Test 2: got {g2}, expected {expected2}")

    # ── Test 3: All positive gaps → returns 0.0 ──
    df3 = pd.DataFrame({
        "open": [100, 105, 110, 108],
        "close": [98, 103, 107, 109],
    })
    g3 = calculate_g_worst(df3)
    if g3 != 0.0:
        errors.append(f"Test 3: got {g3}, expected 0.0")

    # ── Test 4: Too few rows ──
    df4 = pd.DataFrame({"open": [100], "close": [101]})
    try:
        calculate_g_worst(df4)
        errors.append("Test 4: should have raised ValueError")
    except ValueError:
        pass  # expected

    # ── Test 5: Works with DatetimeIndex ──
    df5 = pd.DataFrame({
        "open": np.random.randn(50) + 100,
        "close": np.random.randn(50) + 100,
    })
    result = calculate_g_worst(df5)
    if not isinstance(result, float):
        errors.append(f"Test 5: return type {type(result)}, expected float")
    if result < 0:
        errors.append(f"Test 5: result {result} must be non-negative")

    return errors


errors = verify_all()
print(f"Errors: {len(errors)}")
for e in errors:
    print(f"  FAIL: {e}")
if not errors:
    print("ALL gap_risk tests PASSED")
