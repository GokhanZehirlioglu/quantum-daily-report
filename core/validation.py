"""
Strict data validation for the Decision Support Engine.

Every raw data point that enters the system from ANY provider MUST pass
through `validate_daily_data()` before it can be consumed by downstream
layers (indicators, signals, reports).

Validation rules (all mandatory):
    1. Volume > 0
    2. High > Low
    3. Close is not None / NaN
    4. Returned date matches the requested target_date
"""

from __future__ import annotations

from datetime import date as date_type
from typing import Any, Optional

import numpy as np

from core.exceptions import InvalidDataError

# ─── VALIDATION RULES (single source of truth) ────────────────

_VALIDATION_RULES: list[dict[str, Any]] = [
    {
        "name": "volume_positive",
        "description": "Volume must be strictly greater than zero.",
        "rule": lambda d: d.get("volume", 0) > 0,
        "field": "volume",
    },
    {
        "name": "high_greater_than_low",
        "description": "High price must be strictly greater than Low price.",
        "rule": lambda d: float(d.get("high", 0)) > float(d.get("low", 0)),
        "field": "high",
    },
    {
        "name": "close_not_null",
        "description": "Close price must be non-null and finite.",
        "rule": lambda d: _is_finite(d.get("close")),
        "field": "close",
    },
    {
        "name": "date_matches_target",
        "description": "Returned data date must match the requested target_date.",
        "rule": lambda d: _normalise_date(d.get("date")) == _normalise_date(d.get("target_date")),
        "field": "date",
    },
]


def _is_finite(value: object) -> bool:
    """Check that a value is not None, not NaN, and finite."""
    if value is None:
        return False
    try:
        v = float(value)  # type: ignore[arg-type]
        return np.isfinite(v)
    except (ValueError, TypeError, OverflowError):
        return False


def _normalise_date(raw: object) -> Optional[str]:
    """Convert various date formats to ISO string (YYYY-MM-DD)."""
    if raw is None:
        return None
    if isinstance(raw, str) and len(raw) >= 10:
        return raw[:10]
    if isinstance(raw, date_type):
        return raw.isoformat()
    if isinstance(raw, (int, float)):
        # Unix timestamp in seconds or milliseconds
        import datetime as dt
        try:
            ts = int(raw)
            if ts > 1_000_000_000_000:  # milliseconds → seconds
                ts //= 1000
            return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).strftime("%Y-%m-%d")
        except (OSError, ValueError, OverflowError):
            return None
    return str(raw) if raw else None


def validate_daily_data(data: dict[str, Any]) -> bool:
    """
    Validate a single daily OHLCV data point against all strict rules.

    Args:
        data: A dictionary with at minimum the keys
              ``open``, ``high``, ``low``, ``close``, ``volume``, ``date``,
              and **optionally** ``target_date`` (injected by the caller).

    Returns:
        ``True`` if all validation rules pass.

    Raises:
        InvalidDataError: On the FIRST rule that fails, with the field name,
                          offending value, and the violated rule identifier.

    Example:
        >>> validate_daily_data({
        ...     "open": 100.0, "high": 105.0, "low": 99.0,
        ...     "close": 103.5, "volume": 1_000_000,
        ...     "date": "2026-06-10", "target_date": "2026-06-10",
        ... })
        True
    """
    for rule_def in _VALIDATION_RULES:
        name: str = rule_def["name"]
        passes: bool = rule_def["rule"](data)
        if not passes:
            field: str = rule_def["field"]
            value = data.get(field, "<MISSING>")
            raise InvalidDataError(
                message=(
                    f"Validation failed [{name}]: field='{field}' "
                    f"value={repr(value)} — {rule_def['description']}"
                ),
                field=field,
                value=value,
                rule=name,
            )

    return True


def batch_validate(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Validate a list of daily data points.

    Args:
        items: List of dictionaries, each representing one day of OHLCV data.

    Returns:
        The same list if all items pass validation.

    Raises:
        InvalidDataError: On the first item that fails, with full context.
    """
    for idx, item in enumerate(items):
        try:
            validate_daily_data(item)
        except InvalidDataError as exc:
            raise InvalidDataError(
                message=f"[index={idx}] {exc.args[0]}",
                field=exc.field,
                value=exc.value,
                rule=exc.rule,
            ) from exc
    return items
