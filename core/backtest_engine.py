"""
Backtest Engine — realistic trade simulation with real-world friction.

Key design decisions (non-negotiable):
    1. T+1 Execution: All signals generated on day T are executed at the
       **Open** price on day T+1. Never on the day's Close.
    2. Friction: A ``slippage_pct`` is applied to **both** entry and exit
       prices. Default: 0.003 (0.3%).
    3. Market impact / fill assumptions are not modelled — this is not HFT.
       Slippage is a flat percentage in both directions.

The engine ships with a minimal demo strategy (``rsi_crossover_strategy``)
that goes LONG when RSI > 50 and closes when RSI < 50.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import pandas as pd
import numpy as np

from core.indicators import rsi


# ─── DATA CONTRACTS ─────────────────────────────────────────

@dataclass(frozen=True)
class Trade:
    """A single completed (closed) trade."""

    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    direction: str  # "long" | "short"
    shares: float
    gross_return_pct: float
    net_return_pct: float
    slippage_paid: float


@dataclass
class BacktestResult:
    """Aggregate results from a backtest run."""

    total_return_pct: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    trades: list[Trade] = field(default_factory=list)


# ─── CORE ENGINE ────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    strategy_fn: Callable[[pd.DataFrame, int], Optional[str]],
    slippage_pct: float = 0.003,
    initial_capital: float = 10_000.0,
    verbose: bool = False,
) -> BacktestResult:
    """
    Run a backtest with T+1 execution and slippage.

    Args:
        df: History DataFrame with ``open``, ``high``, ``low``, ``close``
            columns. Must be sorted **oldest → newest** by date.
        strategy_fn: A callable ``fn(df, idx) -> str | None`` that receives
            the full DataFrame and the **current** index (representing day T).
            It must return ``"long"`` to enter a long position, ``"close"``
            to exit the current position, or ``None`` (no action).
            The engine guarantees *idx* is never the last row (T+1 always
            available).
        slippage_pct: Round-trip friction per leg, as a decimal.
            Default 0.003 = 0.3%. Applied to both entry AND exit.
        initial_capital: Starting portfolio value (default $10 000).
        verbose: If ``True``, prints each trade line.

    Returns:
        A ``BacktestResult`` with aggregate stats.

    Raises:
        ValueError: If *df* has fewer than 30 rows (minimum for indicators).
    """
    if len(df) < 30:
        raise ValueError(
            f"Backtest requires at least 30 rows, got {len(df)}."
        )

    df = df.copy()
    capital = initial_capital
    trades: list[Trade] = []
    position: Optional[str] = None  # None | "long"
    entry_price: float = 0.0
    entry_idx: int = 0
    peaks = [initial_capital]

    # Strategy runs from index 1 (first gap check is idx=0→1) through
    # len(df)-2 (T+1 must be available)
    for idx in range(1, len(df) - 1):
        signal = strategy_fn(df, idx)

        # ── ENTER LONG ─────────────────────────────
        if signal == "long" and position is None:
            entry_idx = idx + 1  # T+1
            raw_entry = float(df.iloc[entry_idx]["open"])
            entry_price = raw_entry * (1.0 + slippage_pct)  # slip UP on entry
            shares = capital / entry_price
            position = "long"
            if verbose:
                print(
                    f"  BUY  {df.index[idx].date() if hasattr(df.index[idx], 'date') else idx} "
                    f"→ open next ({df.index[entry_idx].date() if hasattr(df.index[entry_idx], 'date') else entry_idx}) "
                    f"@ ${raw_entry:.2f} slip→ ${entry_price:.2f} | shares={shares:.2f}"
                )

        # ── CLOSE LONG ─────────────────────────────
        elif signal == "close" and position == "long":
            exit_idx = idx + 1  # T+1
            raw_exit = float(df.iloc[exit_idx]["open"])
            exit_price = raw_exit * (1.0 - slippage_pct)  # slip DOWN on exit

            gross_return = (exit_price - entry_price) / entry_price
            net_return = ((exit_price - entry_price) / entry_price) - 2 * slippage_pct
            new_capital = capital * (1.0 + net_return)

            trade = Trade(
                entry_date=str(df.index[entry_idx].date()) if hasattr(df.index[entry_idx], "date") else str(entry_idx),
                exit_date=str(df.index[exit_idx].date()) if hasattr(df.index[exit_idx], "date") else str(exit_idx),
                entry_price=round(entry_price, 4),
                exit_price=round(exit_price, 4),
                direction="long",
                shares=round(shares, 4),
                gross_return_pct=round(gross_return * 100, 2),
                net_return_pct=round(net_return * 100, 2),
                slippage_paid=round(2 * slippage_pct * 100, 2),
            )
            trades.append(trade)
            peaks.append(new_capital)
            capital = new_capital
            position = None

            if verbose:
                print(
                    f"  SELL {df.index[idx].date() if hasattr(df.index[idx], 'date') else idx} "
                    f"→ open next ({df.index[exit_idx].date() if hasattr(df.index[exit_idx], 'date') else exit_idx}) "
                    f"@ ${raw_exit:.2f} slip→ ${exit_price:.2f} | return={net_return*100:.2f}%"
                )

    # ── CLOSE ANY OPEN POSITION AT LAST BAR ────────
    if position == "long":
        final_raw = float(df.iloc[-1]["close"])
        final_price = final_raw * (1.0 - slippage_pct)
        gross_return = (final_price - entry_price) / entry_price
        net_return = ((final_price - entry_price) / entry_price) - 2 * slippage_pct
        capital = capital * (1.0 + net_return)
        peaks.append(capital)

    # ── AGGREGATE METRICS ──────────────────────────
    total_return = ((capital - initial_capital) / initial_capital) * 100

    # Max drawdown
    equity = [initial_capital] + [p for p in peaks]
    running_max = np.maximum.accumulate(equity)
    drawdowns = (running_max - equity) / running_max
    max_dd = float(np.max(drawdowns)) * 100

    # Win rate
    winning = sum(1 for t in trades if t.net_return_pct > 0)
    total_closed = len(trades)

    result = BacktestResult(
        total_return_pct=round(total_return, 2),
        max_drawdown_pct=round(max_dd, 2),
        win_rate=round(winning / total_closed * 100, 1) if total_closed > 0 else 0.0,
        total_trades=total_closed,
        winning_trades=winning,
        losing_trades=total_closed - winning,
        trades=trades,
    )

    if verbose:
        print("\n═══ BACKTEST RESULT ═══")
        print(f"  Return: {result.total_return_pct}% | Max DD: {result.max_drawdown_pct}%")
        print(f"  Win Rate: {result.win_rate}% ({result.winning_trades}/{result.total_trades})")

    return result


# ─── DEMO STRATEGY: RSI CROSSOVER ─────────────────────────

def rsi_crossover_strategy(
    df: pd.DataFrame,
    idx: int,
    rsi_period: int = 14,
    upper: float = 50.0,
    lower: float = 50.0,
) -> Optional[str]:
    """
    Simple RSI crossover demo strategy.

    - When RSI crosses **above** *upper* (50) at day *idx* → enter LONG.
    - When RSI crosses **below** *lower* (50) at day *idx* → CLOSE position.
    - Otherwise → None (no action).

    This is intentionally simplistic — it is a TEST strategy, not a
    production signal. The backtest engine is designed for pluggable
    strategy functions.
    """
    rsi_series = rsi(df["close"], period=rsi_period)

    if idx < 1 or idx >= len(df) - 1:
        return None

    prev_rsi = rsi_series.iloc[idx - 1]
    curr_rsi = rsi_series.iloc[idx]

    if pd.isna(prev_rsi) or pd.isna(curr_rsi):
        return None

    # Buy signal: RSI crosses above 50
    if prev_rsi <= upper and curr_rsi > upper:
        return "long"

    # Sell signal: RSI crosses below 50
    if prev_rsi >= lower and curr_rsi < lower:
        return "close"

    return None
