"""
Position Sizing — risk-based position size calculator.

Core formula:
    S_pos       = r_max / max(g_worst, g_floor)
    S_pos_final = min(S_pos, dynamic_cap)

Where:
    r_max            Max acceptable $ loss per trade (e.g. 1% of portfolio = $100)
    g_worst          Worst historical overnight gap-down (from ``gap_risk.py``)
    g_floor          Minimum denominator floor (default 0.10 = 10%)

    Dynamic cap is applied based on risk regime:
        g_worst >= 0.15 (Cok Yuksek)  →  max 5%  of portfolio
        g_worst >= 0.10 (Yuksek)      →  max 10% of portfolio
        g_worst <  0.10 (Orta/Dusuk)  →  max 15% of portfolio
"""

from __future__ import annotations

from typing import Optional


def _dynamic_cap_pct(g_worst: float) -> float:
    """Return the max position cap as a *fraction* of portfolio (decimal)."""
    if g_worst >= 0.15:
        return 0.05   # 5%
    if g_worst >= 0.10:
        return 0.10   # 10%
    return 0.15       # 15%


def calculate_position_size(
    r_max: float,
    g_worst: float,
    g_floor: float = 0.10,
    portfolio_value: float = 10_000.0,
) -> dict[str, float | bool | str]:
    """
    Calculate the maximum position size for a single trade.

    The cap is applied dynamically according to the risk regime derived
    from ``g_worst`` (see ``_dynamic_cap_pct``).

    Args:
        r_max: Maximum acceptable loss in **dollars** for this trade.
        g_worst: Worst historical gap-down as a decimal (e.g. ``0.20`` = -20%).
        g_floor: Minimum denominator floor (default ``0.10`` = 10%).
        portfolio_value: Total portfolio value in dollars.

    Returns:
        Dict with calculation breakdown:

        .. code:: python

            {
                "position_size": 500.0,       # Final position size ($)
                "position_size_pct": 5.0,     # % of portfolio
                "raw_s_pos": 500.0,           # Before cap
                "g_used": 0.20,               # max(g_worst, g_floor)
                "r_max": 100.0,
                "g_worst": 0.20,
                "g_floor": 0.10,
                "cap_pct": 0.10,              # Fraction used as cap
                "cap_value": 1000.0,          # cap_pct * portfolio_value ($)
                "capped": False,              # Was the raw value capped?
                "cap_reason": "mathematical", # "mathematical" | "risk_limit"
            }

    Example:
        >>> r = calculate_position_size(r_max=100.0, g_worst=0.20)
        >>> r["position_size"]
        500.0
        >>> r["cap_reason"]
        'mathematical'
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

    # Dynamic cap
    cap_pct: float = _dynamic_cap_pct(g_worst)
    cap_value: float = cap_pct * portfolio_value

    if raw_s_pos > cap_value:
        result = cap_value
        capped = True
        cap_reason = "risk_limit"
    else:
        result = raw_s_pos
        capped = False
        cap_reason = "mathematical"

    return {
        "position_size": round(result, 2),
        "position_size_pct": round(result / portfolio_value * 100, 2),
        "raw_s_pos": round(raw_s_pos, 2),
        "g_used": round(g_used, 4),
        "r_max": r_max,
        "g_worst": g_worst,
        "g_floor": g_floor,
        "cap_pct": cap_pct,
        "cap_value": round(cap_value, 2),
        "capped": capped,
        "cap_reason": cap_reason,
    }
