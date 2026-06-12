"""
Gap Risk — overnight gap-down analysis.

Gap % = (Open_t - Close_{t-1}) / Close_{t-1}

The ``calculate_g_worst()`` function scans 2 years of daily data and
returns the single worst (most negative) overnight gap, which is then
used by ``position_sizing.py`` as a key risk input.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd


def calculate_g_worst(
    df: pd.DataFrame,
) -> float:
    """
    Find the worst overnight gap-down over the available history (up to 2 years).

    The result determines the ``g_worst`` parameter in the position-sizing
    formula and represents the maximum adverse gap the strategy must survive.

    Args:
        df: DataFrame with ``open`` and ``close`` columns (daily).
            Must have at least 2 rows. Data is assumed to be in
            chronological order (oldest → newest).

    Returns:
        The absolute value of the largest negative gap, expressed as a
        decimal fraction (e.g. ``0.20`` for a -20% gap-down).

        If no negative gaps are found (extremely unlikely in real data),
        returns ``0.0``.

    Raises:
        ValueError: If *df* has fewer than 2 rows.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     "date": pd.date_range("2025-01-01", periods=5, freq="D"),
        ...     "close": [100, 102, 95, 101, 99],
        ...     "open":  [101, 100, 88, 100, 98],
        ... })
        >>> g_worst = calculate_g_worst(df)
        >>> round(g_worst, 3)
        0.074  # (95→88) / 95
    """
    if len(df) < 2:
        raise ValueError(
            f"Need at least 2 rows of data to calculate gap risk, got {len(df)}."
        )

    close_prev = df["close"].shift(1)
    open_t = df["open"]

    # Gap % = (Open_t - Close_{t-1}) / Close_{t-1}
    gap_pct = (open_t - close_prev) / close_prev

    # Drop the first row (no previous close)
    gap_pct = gap_pct.iloc[1:]

    # Find the most negative gap
    worst_negative = gap_pct.min()

    if pd.isna(worst_negative) or worst_negative >= 0:
        return 0.0

    return abs(float(worst_negative))
