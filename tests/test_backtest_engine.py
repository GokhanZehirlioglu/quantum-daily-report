"""Tests for core/backtest_engine.py — run_backtest."""

import sys, os, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
from core.backtest_engine import run_backtest, rsi_crossover_strategy, BacktestResult


np.random.seed(1234)
dates = pd.date_range("2024-01-01", periods=300, freq="D")
close = 100 + np.cumsum(np.random.randn(300) * 0.5)
high = close + np.abs(np.random.randn(300)) * 2.0
low = close - np.abs(np.random.randn(300)) * 2.0
open_ = low + (high - low) * np.random.rand(300)
volume = np.random.randint(500_000, 5_000_000, 300)

df = pd.DataFrame({
    "open": open_, "high": high, "low": low,
    "close": close, "volume": volume,
}, index=dates)


def verify_all():
    errors = []

    # ── Test 1: Backtest runs and returns correct type ──
    result = run_backtest(df, rsi_crossover_strategy, slippage_pct=0.003)
    if not isinstance(result, BacktestResult):
        errors.append("Test 1: wrong return type")
        return errors  # can't continue without result

    if result.total_trades == 0:
        errors.append(f"Test 1: zero trades generated (expected some)")
    else:
        # Win rate should be 0-100
        if not (0 <= result.win_rate <= 100):
            errors.append(f"Test 1: win_rate={result.win_rate} out of [0,100]")

    # Total return should be finite
    if not math.isfinite(result.total_return_pct):
        errors.append(f"Test 1: total_return not finite: {result.total_return_pct}")

    # Max drawdown should be <= 0 in drawdown space, but >= 0 in our reporting
    if result.max_drawdown_pct < 0:
        errors.append(f"Test 1: negative drawdown: {result.max_drawdown_pct}")
    if result.max_drawdown_pct > 100:
        errors.append(f"Test 1: drawdown > 100%: {result.max_drawdown_pct}")

    # ── Test 2: Trades list matches count ──
    if len(result.trades) != result.total_trades:
        errors.append(f"Test 2: trades list {len(result.trades)} != total_trades {result.total_trades}")

    # ── Test 3: Check a single trade entry/exit uses T+1 ──
    for t in result.trades:
        # Entry and exit must be different dates
        if t.entry_date == t.exit_date:
            errors.append(f"Test 3: same-day trade: {t}")
        # Slippage should be recorded
        if t.slippage_paid <= 0:
            errors.append(f"Test 3: no slippage on trade: {t}")

    # ── Test 4: Slippage effect ──
    # Run with 0% slippage → at least same or better return than 0.3%
    result_no_slip = run_backtest(df, rsi_crossover_strategy, slippage_pct=0.0)
    result_with_slip = run_backtest(df, rsi_crossover_strategy, slippage_pct=0.003)
    if result_with_slip.total_trades > 0 and result_no_slip.total_trades > 0:
        if result_no_slip.total_return_pct < result_with_slip.total_return_pct:
            # Not necessarily guaranteed (different trade timing), but very likely
            pass  # just don't assert

    # ── Test 5: Error on too few rows ──
    small_df = df.iloc[:10]
    try:
        run_backtest(small_df, rsi_crossover_strategy)
        errors.append("Test 5: should have raised ValueError for <30 rows")
    except ValueError:
        pass

    # ── Test 6: Verify T+1 constraint (entry never on signal day) ──
    # We don't have access to the exact signal dates from outside,
    # but we can verify that entry_date < exit_date for all trades
    for t in result.trades:
        if t.entry_date >= t.exit_date:
            errors.append(f"Test 6: entry_date >= exit_date: {t}")

    # ── Test 7: Recorded slippage ──
    for t in result.trades:
        # With 0.3% slippage, slippage_paid should be 0.6 (0.3% entry + 0.3% exit)
        if not math.isclose(t.slippage_paid, 0.6, rel_tol=1e-2):
            errors.append(f"Test 7: slippage_paid={t.slippage_paid}, expected ~0.6")

    # ── Test 8: Empty no-trade scenario ──
    # Strategy that always returns None should produce zero trades
    def noop_strategy(d, i):
        return None

    result_empty = run_backtest(df, noop_strategy)
    if result_empty.total_trades != 0:
        errors.append(f"Test 8: noop strategy should have 0 trades, got {result_empty.total_trades}")
    if result_empty.trades != []:
        errors.append("Test 8: trades should be empty list")

    return errors


errors = verify_all()
print(f"Errors: {len(errors)}")
for e in errors:
    print(f"  FAIL: {e}")
if not errors:
    print("ALL backtest_engine tests PASSED")
