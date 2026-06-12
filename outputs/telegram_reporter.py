"""
Telegram reporter — human-readable, risk-focused market summary.

CRITICAL RULE: This module NEVER says "Al" (Buy) or "Sat" (Sell).
It reports risk regimes, technical scores, and gap risk so the user
can make their OWN informed decision.

Output follows the mandated template:
    Hisse: {SYMBOL} | Teknik Skor: {SCORE}/100
    Trend: {TREND_LABEL}
    Risk Rejimi: {REGIME}
    Gap Risk (En Kotu): -%{G_WORST}
    Maksimum Pozisyon: {S_POS}x (Portfoy Limiti)
    Karar: {DECISION}
"""

from __future__ import annotations

import os
import requests
from datetime import datetime, timezone
from typing import Any, Optional


# ─── HELPERS ──────────────────────────────────────────────

_TREND_ICON = {
    "Boga": "📐",
    "Ayi": "📐",
    "Karisik / Yatay": "📐",
}

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
        analysis: Combined dict from orchestrator containing ``price``,
                  ``indicators``, ``risk`` sub-dicts.

    Returns:
        HTML-formatted string suitable for Telegram ``parse_mode="HTML"``.
    """
    price = analysis.get("price", {})
    ind = analysis.get("indicators", {})
    risk = analysis.get("risk", {})

    p_last = price.get("last", "?")
    p_chg = price.get("change_pct", 0)
    arrow = "🔺" if p_chg >= 0 else "🔻"

    score = risk.get("composite_score", 0)
    regime_label = risk.get("regime_label", "Belirsiz")
    trend_lbl = risk.get("trend_label", "?")
    g_worst = risk.get("gap_risk_pct", 0)
    s_pos = risk.get("max_position_pct", 0)
    capped = risk.get("position_capped", False)
    decision = risk.get("decision", _regime_verb(regime_label))

    rsi_val = ind.get("momentum", {}).get("rsi", "?")
    rsi_zone = ind.get("momentum", {}).get("rsi_zone", "?")
    macd_type = ind.get("trend", {}).get("macd_signal_type", "bearish")
    macd_ico = "🟢" if macd_type == "bullish" else "🔴"
    bb_sq = ind.get("volatility", {}).get("bb_squeeze", False)
    vol_ratio = ind.get("volume", {}).get("ratio", 0)
    adx = ind.get("trend", {}).get("adx", "?")
    adx_str = ind.get("trend", {}).get("trend_strength", "?")
    adx_lbl = _ADX_LABEL.get(adx_str, "")

    regime_icon = _REGIME_ICON.get(regime_label, "⚪")

    pos_label = f"{s_pos:.1f}%" if s_pos else "Hesaplanamadi"
    if capped:
        pos_label += " (Limitte)"

    lines = [
        f"<b>━━━ {symbol} ━━━</b>",
        f"💰 <b>${p_last}</b> {arrow} %{p_chg:+.2f}",
        f"",
        f"<b>Hisse:</b> {symbol} | <b>Teknik Skor:</b> {score}/100",
        f"<b>Trend:</b> {trend_lbl} {macd_ico} | ADX: {adx} {adx_lbl}",
        f"<b>RSI(14):</b> {rsi_val} {_rsi_emoji(rsi_val)} ({rsi_zone})",
        f"<b>Risk Rejimi:</b> {regime_icon} {regime_label}",
        f"<b>Gap Risk (En Kotu):</b> -%{g_worst:.1f}",
        f"<b>Maksimum Pozisyon:</b> {pos_label}",
    ]

    if bb_sq:
        lines.append(f"<b>Durum:</b> BB Squeeze — volatilite patlamasi beklenebilir ⚠️")

    if vol_ratio and vol_ratio > 2.0:
        lines.append(f"<b>Hacim:</b> Ortalamanin {vol_ratio}x uzerinde — dikkat 🔥")
    elif vol_ratio and vol_ratio < 0.5:
        lines.append(f"<b>Hacim:</b> Ortalamanin altinda ({vol_ratio}x) 😴")

    lines.append("")
    lines.append(f"📋 <b>Karar:</b> {decision}")

    return "\n".join(lines)


# ─── FULL REPORT ─────────────────────────────────────────

def build_report(
    symbol_blocks: list[tuple[str, str, dict[str, Any]]],  # [(symbol, name, analysis_dict)]
    summary_table: str = "",
) -> str:
    """
    Build the full Telegram report from per-symbol blocks.

    Args:
        symbol_blocks: List of (symbol, company_name, analysis_dict) tuples.
        summary_table: Pre-formatted summary table string (optional).

    Returns:
        Complete HTML report string.
    """
    now = datetime.now(timezone.utc)

    lines = [
        f"📊 <b>KUANTUM HISSE RAPORU</b>",
        f"📅 {now.strftime('%d.%m.%Y')} ⏰ {now.strftime('%H:%M UTC')}",
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
    """
    Send *text* to Telegram via the Bot API.

    Splits messages exceeding 4000 characters into multiple chunks.

    Args:
        text: The formatted report.
        bot_token: Telegram Bot API token.
        chat_id: Target chat ID.
        parse_mode: ``"HTML"`` (default) or ``"MarkdownV2"``.

    Returns:
        ``True`` on success.
    """
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
