"""
Structured JSON report — machine-readable output for agent consumption.

Every symbol analysis produces a deterministic JSON document containing
all raw indicator values, the composite score, gap risk, and position
sizing data. The agent (market-analyst) reads this JSON to reason about
the market without having to re-parse human text.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"
DEFAULT_FILENAME = "analysis_data.json"


def generate_json(
    symbol: str,
    price_data: dict[str, Any],
    indicators: dict[str, Any],
    gap_risk: dict[str, Any],
    position_sizing: dict[str, Any],
    composite_score: int,
    regime_label: str,
    trend_label: str,
    target_date: str,
) -> dict[str, Any]:
    """
    Build a structured JSON document for one symbol.

    Args:
        symbol: Ticker symbol (e.g. ``"QBTS"``).
        price_data: Dict with ``last``, ``open``, ``high``, ``low``,
                    ``change_pct``, ``change_5d``.
        indicators: Dict with all computed indicator values (SMA, RSI,
                    MACD, ATR, volumes).
        gap_risk: Dict with ``g_worst`` and optional metadata.
        position_sizing: Dict from ``calculate_position_size()``.
        composite_score: ``int`` 0–100 from ``scoring.py``.
        regime_label: Risk regime string (e.g. ``"Yuksek Risk"``).
        trend_label: Trend direction string (e.g. ``"Boga"``).
        target_date: ISO trading date string.

    Returns:
        The JSON-serializable dict (also written to disk).
    """
    now = datetime.now(timezone.utc)

    document: dict[str, Any] = {
        "engine": "quantum-decision-support-engine",
        "version": "0.3.0",
        "timestamp": now.isoformat(),
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "symbol": symbol.upper(),
        "target_date": target_date,
        "price": {
            "last": price_data.get("last"),
            "open": price_data.get("open"),
            "high": price_data.get("high"),
            "low": price_data.get("low"),
            "change_pct": price_data.get("change_pct"),
            "change_5d_pct": price_data.get("change_5d"),
        },
        "indicators": {
            "trend": {
                "sma_20": indicators.get("sma_20"),
                "sma_50": indicators.get("sma_50"),
                "ema_12": indicators.get("ema_12"),
                "ema_26": indicators.get("ema_26"),
                "vs_sma20_pct": indicators.get("vs_sma20_pct"),
                "macd": indicators.get("macd"),
                "macd_signal": indicators.get("macd_signal"),
                "macd_hist": indicators.get("macd_hist"),
                "macd_bullish": indicators.get("macd_bullish"),
                "macd_signal_type": "bullish" if indicators.get("macd_bullish") else "bearish",
                "adx": indicators.get("adx"),
                "trend_direction": indicators.get("trend_dir"),
                "trend_strength": indicators.get("adx_strength"),
            },
            "momentum": {
                "rsi": indicators.get("rsi"),
                "rsi_zone": indicators.get("rsi_zone"),
            },
            "volatility": {
                "atr": indicators.get("atr"),
                "atr_pct": indicators.get("atr_pct"),
                "bb_upper": indicators.get("bb_upper"),
                "bb_mid": indicators.get("bb_mid"),
                "bb_lower": indicators.get("bb_lower"),
                "bb_position_pct": indicators.get("bb_position"),
                "bb_squeeze": indicators.get("bb_squeeze", False),
            },
            "volume": {
                "last": indicators.get("vol_last"),
                "avg_5d": indicators.get("vol_avg5"),
                "ratio": indicators.get("vol_ratio"),
                "obv_trend": indicators.get("obv_trend"),
            },
            "levels": {
                "pivot": indicators.get("pivot"),
                "r1": indicators.get("r1"),
                "s1": indicators.get("s1"),
                "r2": indicators.get("r2"),
                "s2": indicators.get("s2"),
                "high_20d": indicators.get("high_20d"),
                "low_20d": indicators.get("low_20d"),
                "fib_382": indicators.get("fib_382"),
                "fib_618": indicators.get("fib_618"),
            },
        },
        "risk": {
            "composite_score": composite_score,
            "regime_label": regime_label,
            "trend_label": trend_label,
            "gap_risk_pct": round(gap_risk.get("g_worst", 0) * 100, 1),
            "max_position_size": position_sizing.get("position_size"),
            "max_position_pct": position_sizing.get("position_size_pct"),
            "position_capped": position_sizing.get("capped"),
        },
        "meta": {
            "data_source": "yfinance" if not gap_risk.get("provider") else gap_risk["provider"],
            "rule_count": _count_active_signals(indicators),
        },
    }

    return document


def _count_active_signals(indicators: dict[str, Any]) -> int:
    """Count how many warning/alert conditions exist."""
    count = 0
    rsi = indicators.get("rsi")
    if rsi is not None and (rsi >= 70 or rsi <= 30):
        count += 1
    if indicators.get("bb_squeeze"):
        count += 1
    if indicators.get("vol_ratio") is not None and indicators["vol_ratio"] > 2.0:
        count += 1
    return count


def save_json(
    document: dict[str, Any],
    filename: str = DEFAULT_FILENAME,
) -> str:
    """
    Write the JSON document to disk.

    Args:
        document: The JSON-serializable dict.
        filename: Output filename (default ``analysis_data.json``).

    Returns:
        The absolute path of the saved file.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(document, f, indent=2, ensure_ascii=False)

    return str(filepath)


def generate_batch_json(
    symbol_results: list[dict[str, Any]],
    output_path: str | None = None,
) -> dict[str, Any]:
    """
    Build a multi-symbol aggregated JSON document.

    Args:
        symbol_results: List of documents returned by ``generate_json()``
                        for each symbol.

    Returns:
        The aggregated JSON dict.
    """
    now = datetime.now(timezone.utc)

    batch: dict[str, Any] = {
        "engine": "quantum-decision-support-engine",
        "version": "0.3.0",
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "symbol_count": len(symbol_results),
        "symbols": {r["symbol"]: r for r in symbol_results},
        "summary": {
            "highest_score": max((r.get("risk", {}).get("composite_score", 0) for r in symbol_results), default=0),
            "lowest_score": min((r.get("risk", {}).get("composite_score", 0) for r in symbol_results), default=0),
        },
    }

    if output_path:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(batch, f, indent=2, ensure_ascii=False)

    return batch
