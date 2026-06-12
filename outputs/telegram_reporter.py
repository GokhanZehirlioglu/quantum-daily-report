"""
Telegram reporter — human-readable, risk-focused market summary.

CRITICAL RULE: This module NEVER says "Al" (Buy) or "Sat" (Sell).
It reports risk regimes, technical scores, and gap risk so the user
can make their OWN informed decision.

Formatting rules (Sprint 3.1):
    - All floats displayed at max 1 decimal place.
    - None indicators are HIDDEN (not shown as "None").
    - Header shows BOTH report generation time and data date.
    - Position line states whether the cap was mathematical or by risk limit.
"""

from __future__ import annotations

import os
import requests
from datetime import datetime, timezone
from typing import Any, Optional


# ─── HELPERS ──────────────────────────────────────────────

_REGIME_ICON = {
    "Dusuk Risk": "🟢",
    "Orta Risk": "🟡",
    "Yuksek Risk": "🟠",
    "Cok Yuksek Risk": "🔴",
}

_ADX_LABEL = {
    "very_strong": "Cok Guclu 🔥",
    "strong": "Guclu 💪",
    "moderate": "Orta ⚡",
    "weak": "Zayif 😴",
}


def _regime_verb(regime: str) -> str:
    """Return the Turkish decision string for a risk regime."""
    mapping = {
        "Dusuk Risk": "Portfoy icin uygun kosullar. Mevcut pozisyonlar korunabilir.",
        "Orta Risk": "Teyit beklenmeli. Yeni alim icin ek onay gerekli.",
        "Yuksek Risk": "Yeni alim onerilmez. Mevcut pozisyonlar gozden gecirilmeli.",
        "Cok Yuksek Risk": "Yeni alim sadece premarket kontrolunden sonra yapilabilir.",
    }
    return mapping.get(regime, "Piyasa kosullari belirsiz.")


def _rsi_emoji(rsi: Optional[float]) -> str:
    if rsi is None:
        return "⚪"
    if rsi >= 70:
        return "🔴"
    if rsi <= 30:
        return "🟢"
    if rsi >= 60:
        return "🟠"
    return "⚪"


def _fmt(val: Any, decimals: int = 1) -> str:
    """Format a number to ``decimals`` decimal places, or return ``"?"``."""
    if val is None:
        return "?"
    try:
        return f"{float(val):.{decimals}f}"
    except (ValueError, TypeError):
        return "?"


# ─── PER-SYMBOL BLOCK ────────────────────────────────────

def format_symbol_block(
    symbol: str,
    name: str,
    analysis: dict[str, Any],
) -> str:
    """
    Format one symbol's analysis block for Telegram.

    Args:
        symbol: Ticker (e.g. ``"QBTS"``).
        name: Company name.
        analysis: Combined dict from orchestrator.
    """
    price = analysis.get("price", {})
    ind = analysis.get("indicators", {})
    risk = analysis.get("risk", {})
    gap_meta = analysis.get("gap_metadata", {})

    p_last = price.get("last", "?")
    p_chg = price.get("change_pct", 0)
    arrow = "🔺" if p_chg >= 0 else "🔻"

    score = risk.get("composite_score", 0)
    regime_label = risk.get("regime_label", "Belirsiz")
    trend_lbl = risk.get("trend_label", "?")
    g_worst = risk.get("gap_risk_pct", 0)
    s_pos = risk.get("max_position_pct", 0)
    capped = risk.get("position_capped", False)
    cap_reason = risk.get("cap_reason", "mathematical")
    decision = risk.get("decision", _regime_verb(regime_label))

    regime_icon = _REGIME_ICON.get(regime_label, "⚪")

    # ── RSI ──
    rsi_val = ind.get("momentum", {}).get("rsi")
    rsi_zone = ind.get("momentum", {}).get("rsi_zone", "?")

    # ── Trend line (conditional: hide None components) ──
    trend_parts = [f"<b>Trend:</b> {trend_lbl}"]
    macd_type = ind.get("trend", {}).get("macd_signal_type", "bearish")
    macd_ico = "🟢" if macd_type == "bullish" else "🔴"
    trend_parts.append(macd_ico)
    # ADX — only if non-None
    adx = ind.get("trend", {}).get("adx")
    if adx is not None:
        adx_str = ind.get("trend", {}).get("trend_strength")
        adx_lbl = _ADX_LABEL.get(adx_str, "")
        trend_parts.append(f"| ADX: {_fmt(adx, 0)} {adx_lbl}")
    trend_line = " ".join(trend_parts)

    # ── Position label ──
    if s_pos:
        if capped:
            if cap_reason == "risk_limit":
                pos_label = f"%{s_pos:.1f} (Risk Limiti Devrede)"
            else:
                pos_label = f"%{s_pos:.1f} (Matematiksel Limit)"
        else:
            pos_label = f"%{s_pos:.1f} (Matematiksel Limit)"
    else:
        pos_label = "Hesaplanamadi"

    # ── Gap warning ──
    gap_warning = gap_meta.get("warning_text", "")

    lines = [
        f"<b>━━━ {symbol} ━━━</b>",
        f"💰 <b>${p_last}</b> {arrow} %{_fmt(p_chg, 1)}",
        f"",
        f"<b>Hisse:</b> {symbol} | <b>Teknik Skor:</b> {score}/100",
        trend_line,
    ]

    # RSI — only if non-None
    if rsi_val is not None:
        lines.append(
            f"<b>RSI(14):</b> {_fmt(rsi_val)} {_rsi_emoji(rsi_val)} ({rsi_zone})"
        )

    lines.append(f"<b>Risk Rejimi:</b> {regime_icon} {regime_label}")
    lines.append(f"<b>Gap Risk (En Kotu):</b> -%{_fmt(g_worst, 1)}")

    if gap_warning:
        lines.append(f"<b>{gap_warning}</b>")

    lines.append(f"<b>Maksimum Pozisyon:</b> {pos_label}")

    # ── Extra signals ──
    bb_sq = ind.get("volatility", {}).get("bb_squeeze", False)
    if bb_sq:
        lines.append("<b>Durum:</b> BB Squeeze — volatilite patlamasi beklenebilir ⚠️")

    vol_ratio = ind.get("volume", {}).get("ratio")
    if vol_ratio is not None:
        if vol_ratio > 2.0:
            lines.append(f"<b>Hacim:</b> Ortalamanin {_fmt(vol_ratio)}x uzerinde — dikkat 🔥")
        elif vol_ratio < 0.5:
            lines.append(f"<b>Hacim:</b> Ortalamanin altinda ({_fmt(vol_ratio)}x) 😴")

    lines.append("")
    lines.append(f"📋 <b>Karar:</b> {decision}")

    return "\n".join(lines)


# ─── FULL REPORT ─────────────────────────────────────────

def build_report(
    symbol_blocks: list[tuple[str, str, dict[str, Any]]],
    summary_table: str = "",
    data_date: str = "",
) -> str:
    """
    Build the full Telegram report from per-symbol blocks.

    Args:
        symbol_blocks: List of (symbol, company_name, analysis_dict) tuples.
        summary_table: Pre-formatted summary table string (optional).
        data_date: Trading date string for the data (e.g. ``"2026-06-11"``).

    Returns:
        Complete HTML report string.
    """
    now = datetime.now(timezone.utc)

    header_lines = [
        f"📊 <b>KUANTUM HISSE RAPORU</b>",
        f"Rapor Uretim: {now.strftime('%H:%M UTC')}",
    ]
    if data_date:
        header_lines.append(f"Veri Tarihi: {data_date} EOD (Kapanis)")

    lines = [
        *header_lines,
        f"🤖 <b>Karar Destek Motoru v0.3.0</b>",
        f"",
        f"<i>Hicbir sey alim/satim tavsiyesi degildir. Risk yonetimi onceliklidir.</i>",
        f"",
    ]

    for symbol, name, analysis in symbol_blocks:
        lines.append(format_symbol_block(symbol, name, analysis))
        lines.append("")

    if summary_table:
        lines.append(summary_table)

    lines.append(f"\n{chr(8212)*20}")
    lines.append(
        f"🚀 <i>Uc hisse de kuantum bilisim sektorunde. "
        f"Yuksek volatilite beklenir. Pozisyon buyuklugu risk rejimine gore "
        f"ayarlanmalidir.</i>"
    )

    return "\n".join(lines)


# ─── TELEGRAM SENDER ─────────────────────────────────────

def send_report(
    text: str,
    bot_token: str,
    chat_id: str,
    parse_mode: str = "HTML",
) -> bool:
    """Send *text* to Telegram via the Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    for chunk in _chunk_text(text, 4000):
        try:
            resp = requests.post(
                url,
                json={
                    "chat_id": chat_id,
                    "text": chunk,
                    "parse_mode": parse_mode,
                    "disable_web_page_preview": True,
                },
                timeout=15,
            )
            data = resp.json()
            if not data.get("ok"):
                print(f"[Telegram] API error: {data.get('description', 'unknown')}")
                return False
        except requests.RequestException as exc:
            print(f"[Telegram] Network error: {exc}")
            return False

    return True


def _chunk_text(text: str, size: int):
    """Yield chunks of *text* up to *size* characters, splitting at newlines."""
    while len(text) > size:
        split_at = text.rfind("\n", 0, size)
        if split_at == -1:
            split_at = size
        yield text[:split_at]
        text = text[split_at:]
    yield text
