"""
Composite Technical Score (0–100).

Quantifies overall bullish/bearish posture on a deterministic scale.
Used by the Telegram reporter to label risk regimes and by the JSON
generator for structured output.

Components:
    Trend (40 pts)   — MACD direction, SMA alignment, price vs SMA
    Momentum (30 pts) — RSI zone (overbought/oversold proximity)
    Volume & Risk (30 pts) — volume relative to average, ATR normality
"""

from __future__ import annotations

from typing import Any, Optional


def calculate_composite_score(indicators_data: dict[str, Any]) -> int:
    """
    Compute a 0–100 composite technical score from pre-computed indicators.

    Args:
        indicators_data: Dict with keys:
            - ``macd_bullish`` (bool)
            - ``vs_sma20_pct`` (float): % distance from SMA20
            - ``sma_20``, ``sma_50`` (float or None)
            - ``rsi`` (float)
            - ``vol_ratio`` (float): current volume / avg(5) volume
            - ``atr_pct`` (float): ATR as % of price

    Returns:
        Integer score 0–100.

    Score legend:
        - 80–100: Strong bullish configuration
        - 60–79:  Moderately bullish
        - 40–59:  Neutral / mixed signals
        - 20–39:  Moderately bearish
        - 0–19:   Strong bearish configuration
    """
    trend_pts = _score_trend(indicators_data)
    momentum_pts = _score_momentum(indicators_data)
    volume_pts = _score_volume_risk(indicators_data)

    total = trend_pts + momentum_pts + volume_pts
    return max(0, min(100, total))


# ─── COMPONENT SCORERS ────────────────────────────────────

def _score_trend(d: dict[str, Any]) -> int:
    """
    Trend component — max 40 pts.

    Rules:
        - MACD bullish → +15
        - Price above SMA20 → +10
        - SMA20 above SMA50 (golden cross status) → +10
        - Price above SMA50 → +5
    """
    score = 0

    # MACD direction
    if d.get("macd_bullish"):
        score += 15

    # Price vs SMA20
    vs_sma20 = d.get("vs_sma20_pct")
    if vs_sma20 is not None and vs_sma20 > 0:
        score += 10
    elif vs_sma20 is not None and vs_sma20 > -2:
        score += 5  # within 2% below SMA20

    # SMA alignment
    sma20 = d.get("sma_20")
    sma50 = d.get("sma_50")
    if sma20 is not None and sma50 is not None and sma20 > sma50:
        score += 10

    # Price vs SMA50
    price = d.get("price")
    if price is not None and sma50 is not None and price > sma50:
        score += 5

    return score


def _score_momentum(d: dict[str, Any]) -> int:
    """
    Momentum component — max 30 pts.

    Rules (RSI-based):
        - RSI >= 70 (overbought, strong momentum) → 30
        - RSI 60–69 → 25
        - RSI 50–59 → 20
        - RSI 40–49 → 10
        - RSI 30–39 →  5
        - RSI < 30 →  0
    """
    rsi_val = d.get("rsi")
    if rsi_val is None:
        return 10  # neutral default

    if rsi_val >= 70:
        return 30
    elif rsi_val >= 60:
        return 25
    elif rsi_val >= 50:
        return 20
    elif rsi_val >= 40:
        return 10
    elif rsi_val >= 30:
        return 5
    return 0


def _score_volume_risk(d: dict[str, Any]) -> int:
    """
    Volume & Risk component — max 30 pts.

    Rules:
        - Volume ratio > 1.5 (institutional interest) → +15
        - Volume ratio > 1.0 (above average) → +10
        - Volume ratio > 0.7 (normal) → +5
        - ATR % between 1% and 5% (healthy volatility) → +15
        - ATR % ≤ 1% (too quiet) → +5
        - ATR % > 8% (extreme) → +0  (dangerous)
    """
    score = 0

    # Volume
    vol_ratio = d.get("vol_ratio")
    if vol_ratio is not None:
        if vol_ratio > 1.5:
            score += 15
        elif vol_ratio > 1.0:
            score += 10
        elif vol_ratio > 0.7:
            score += 5
        # else: way below avg → +0

    # ATR normality
    atr_pct = d.get("atr_pct")
    if atr_pct is not None:
        if 1.0 <= atr_pct <= 5.0:
            score += 15
        elif atr_pct < 1.0:
            score += 5
        elif atr_pct <= 8.0:
            score += 5  # high but manageable
        # > 8% → extreme → +0

    return score


# ─── ZONE / LABEL HELPERS ────────────────────────────────

def score_to_regime(score: int) -> tuple[str, str]:
    """
    Convert numeric score to (regime_label, risk_emoji).

    Returns:
        (label, emoji) e.g. ("Yuksek Risk", "🔴")
    """
    if score >= 80:
        return "Dusuk Risk", "🟢"
    elif score >= 60:
        return "Orta Risk", "🟡"
    elif score >= 40:
        return "Yuksek Risk", "🟠"
    return "Cok Yuksek Risk", "🔴"


def trend_label(
    macd_bullish: Optional[bool],
    price_vs_sma20: Optional[float],
) -> str:
    """Return human-readable trend direction label."""
    if macd_bullish and (price_vs_sma20 is not None and price_vs_sma20 > 0):
        return "Boga"
    if not macd_bullish and (price_vs_sma20 is not None and price_vs_sma20 < 0):
        return "Ayi"
    return "Karisik / Yatay"
