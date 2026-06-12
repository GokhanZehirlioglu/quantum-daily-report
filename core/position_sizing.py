"""
Position Sizing — risk-based position size calculator.

Formula (agreed in design):
    S_pos       = r_max / max(g_worst, g_floor)
    S_pos_final = min(S_pos, max_position_cap)

Where:
    r_max            Max acceptable $ loss per trade (e.g. 1% of portfolio = $100)
    g_worst          Worst historical overnight gap-down (from ``gap_risk.py``)
    g_floor          Minimum floor for g_worst (default 0.10 = 10% — prevents
                     infinite leverage on tiny gaps)
    max_position_cap Hard ceiling as fraction of portfolio (default 0.15 = 15%)
"""

from __future__ import annotations

from typing import Optional


def calculate_position_size(
    r_max: float,
    g_worst: float,
    g_floor: float = 0.10,
    max_position_cap: float = 0.15,
    portfolio_value: float = 10_000.0,
) -> dict[str, float]:
    """
    Calculate the maximum position size for a single trade.

    The formula ensures that even in the worst historical gap-down scenario,
    the loss on this single position stays within ``r_max``.

    Args:
        r_max: Maximum acceptable loss in **dollars** for this trade.
               (e.g. ``100.0`` = 1% of a $10 000 portfolio).
        g_worst: Worst historical gap-down as a decimal (e.g. ``0.20`` = -20%).
                 Output of ``gap_risk.calculate_g_worst()``.
        g_floor: Minimum denominator floor (default ``0.10`` = 10%).
                 Prevents ``S_pos`` from exploding when a stock has very
                 small historical gaps.
        max_position_cap: Hard cap expressed as a **fraction** of
                          ``portfolio_value`` (default ``0.15`` = 15%).
        portfolio_value: Total portfolio value in dollars.
                         Used to compute the dollar value of the cap.

    Returns:
        A dict with calculation breakdown:

        .. code:: python

            {
                "position_size": 500.0,       # Final position size ($)
                "position_size_pct": 5.0,     # % of portfolio
                "raw_s_pos": 500.0,           # Before cap
                "g_used": 0.20,               # max(g_worst, g_floor)
                "r_max": 100.0,
                "g_worst": 0.20,
                "g_floor": 0.10,
                "cap_value": 1500.0,          # max_position_cap * portfolio_value
                "capped": False,              # Was the raw value capped?
            }

    Example:
        >>> result = calculate_position_size(r_max=100.0, g_worst=0.20)
        >>> result["position_size"]
        500.0
        >>> result["position_size_pct"]
        5.0
    """
    # Validate inputs
    if r_max <= 0:
        raise ValueError(f"r_max must be > 0, got {r_max}")
    if g_worst < 0:
        raise ValueError(f"g_worst must be >= 0, got {g_worst}")
    if portfolio_value <= 0:
        raise ValueError(f"portfolio_value must be > 0, got {portfolio_value}")

    g_used: float = max(g_worst, g_floor)

    # Core formula: S_pos = r_max / max(g_worst, g_floor)
    raw_s_pos: float = r_max / g_used

    cap_value: float = max_position_cap * portfolio_value

    if raw_s_pos > cap_value:
        result: float = cap_value
        capped: bool = True
    else:
        result = raw_s_pos
        capped = False

    return {
        "position_size": round(result, 2),
        "position_size_pct": round(result / portfolio_value * 100, 2),
        "raw_s_pos": round(raw_s_pos, 2),
        "g_used": round(g_used, 4),
        "r_max": r_max,
        "g_worst": g_worst,
        "g_floor": g_floor,
        "cap_value": round(cap_value, 2),
        "capped": capped,
    }
