"""
Gap Risk — overnight gap-down analysis.

Gap % = (Open_t - Close_{t-1}) / Close_{t-1}

The ``calculate_g_worst()`` function scans available data and returns the
single worst overnight gap-down. It requires a minimum of 500 trading days
(~2 years) for a reliable estimate; anything less triggers a warning.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

MIN_REQUIRED_DAYS: int = 500


def calculate_g_worst(
    df: pd.DataFrame,
) -> tuple[float, dict[str, Any]]:
    """
    Find the worst overnight gap-down over available history.

    Args:
        df: DataFrame with ``open`` and ``close`` columns (daily).
            Chronological order (oldest → newest). Must have >= 2 rows.

    Returns:
        ``(g_worst, metadata)`` where:

        - ``g_worst``: Absolute value of the largest negative gap as a decimal
          (e.g. ``0.20`` for -20%). Returns ``0.0`` if no negative gaps found.
        - ``metadata``: Dict with keys:
            - ``days_analysed``: Number of trading days used.
            - ``short_data_warning``: ``True`` if fewer than ``MIN_REQUIRED_DAYS``.
            - ``warning_text``: Human-readable warning or ``""``.

    Raises:
        ValueError: If *df* has fewer than 2 rows.

    Example:
        >>> import pandas as pd
        >>> df = pd.DataFrame({
        ...     "close": [100, 102, 95, 101, 99],
        ...     "open":  [101, 100, 88, 100, 98],
        ... })
        >>> g, meta = calculate_g_worst(df)
        >>> round(g, 3), meta["short_data_warning"]
        (0.074, True)
    """
    if len(df) < 2:
        raise ValueError(
            f"Need at least 2 rows of data to calculate gap risk, got {len(df)}."
        )

    n_days = len(df)
    close_prev = df["close"].shift(1)
    open_t = df["open"]

    # Gap % = (Open_t - Close_{t-1}) / Close_{t-1}
    gap_pct = (open_t - close_prev) / close_prev
    gap_pct = gap_pct.iloc[1:]  # drop first row (no previous close)

    worst_negative = gap_pct.min()

    if pd.isna(worst_negative) or worst_negative >= 0:
        g_worst = 0.0
    else:
        g_worst = abs(float(worst_negative))

    short_warning = n_days < MIN_REQUIRED_DAYS
    metadata = {
        "days_analysed": n_days - 1,  # gaps computed = rows - 1
        "short_data_warning": short_warning,
        "warning_text": (
            f"⚠️ Uyari: Gap risk kisa veri ile ({n_days} gun) hesaplandi. "
            f"Minimum {MIN_REQUIRED_DAYS} gun onerilir."
        ) if short_warning else "",
    }

    return g_worst, metadata
