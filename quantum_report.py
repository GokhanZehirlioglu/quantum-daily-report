#!/usr/bin/env python3
"""
Quantum Stocks Daily Technical Report
======================================
Symbols: QBTS, RGTI, IONQ
Schedule: Every weekday, 1.5 hours after US market open
Delivery: Telegram Bot

Indicators:
- RSI (14) — Overbought >70 / Oversold <30
- Bollinger Bands (20,2)
- Volume analysis
"""

import yfinance as yf
import pandas as pd
import numpy as np
import requests
import os
import sys
from datetime import datetime, timedelta
import json

# Windows konsolunda Türkçe karakter hatasını önle
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── CONFIG ───────────────────────────────────────────
SYMBOLS = ["QBTS", "RGTI", "IONQ"]
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
DEBUG = os.environ.get("DEBUG", "").lower() == "true"

# ─── TECHNICAL INDICATORS ─────────────────────────────

def calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Wilder's smoothed RSI."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def calc_bollinger(series: pd.Series, period: int = 20, std_mult: float = 2.0):
    """Returns (middle, upper, lower) Bollinger Bands."""
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    return sma, sma + std_mult * std, sma - std_mult * std


def rsi_zone_name(rsi_val: float) -> str:
    if rsi_val >= 70:
        return "🔴 AŞIRI ALIM"
    elif rsi_val <= 30:
        return "🟢 AŞIRI SATIM"
    elif rsi_val >= 60:
        return "🟠 Yukarı yönlü"
    elif rsi_val <= 40:
        return "🟡 Aşağı yönlü"
    else:
        return "⚪ Nötr"


def bb_assessment(price: float, upper: float, lower: float, sma: float) -> str:
    """Where is price relative to Bollinger Bands?"""
    if price >= upper * 0.995:
        return "Üst bandı test ediyor 🔺"
    elif price <= lower * 1.005:
        return "Alt bandı test ediyor 🔻"
    elif price > sma:
        return f"Orta bandın üstünde (trend ↑)"
    else:
        return f"Orta bandın altında (trend ↓)"


# ─── MAIN ANALYSIS ────────────────────────────────────

def analyze_symbol(sym: str) -> dict | None:
    """Fetch data and compute all indicators for one symbol."""
    try:
        ticker = yf.Ticker(sym)
        hist = ticker.history(period="1mo", interval="1d")

        if hist.empty or len(hist) < 20:
            print(f"  [!] {sym}: yetersiz veri ({len(hist)} bar)")
            return None

        close = hist["Close"]
        volume = hist["Volume"]
        high = hist["High"]
        low = hist["Low"]

        # ── current day ──
        cur = float(close.iloc[-1])
        prev = float(close.iloc[-2])
        chg_pct = ((cur - prev) / prev) * 100.0

        day_open = float(hist["Open"].iloc[-1])
        day_high = float(high.iloc[-1])
        day_low = float(low.iloc[-1])

        # ── RSI ──
        rsi = calc_rsi(close, 14)
        rsi_now = round(float(rsi.iloc[-1]), 2)
        rsi_ma = round(float(rsi.rolling(14).mean().iloc[-1]), 2)

        # ── Bollinger ──
        bb_mid, bb_up, bb_lo = calc_bollinger(close, 20, 2.0)
        bb_mid_v = round(float(bb_mid.iloc[-1]), 2)
        bb_up_v = round(float(bb_up.iloc[-1]), 2)
        bb_lo_v = round(float(bb_lo.iloc[-1]), 2)

        # ── price vs SMA20 distance ──
        sma_dist = round(((cur - bb_mid_v) / bb_mid_v) * 100.0, 2)

        # ── BB position % ──
        bb_range = bb_up_v - bb_lo_v
        bb_pos = round(((cur - bb_lo_v) / bb_range) * 100.0, 1) if bb_range > 0 else 50.0

        # ── volume ──
        vol_cur = int(volume.iloc[-1])
        vol_avg5 = int(volume.iloc[-6:-1].mean()) if len(volume) >= 6 else vol_cur
        vol_ratio = round(vol_cur / vol_avg5, 1) if vol_avg5 > 0 else 1.0

        # ── 5-day price change ──
        if len(close) >= 6:
            chg_5d = round(((cur - float(close.iloc[-6])) / float(close.iloc[-6])) * 100.0, 2)
        else:
            chg_5d = 0.0

        # ── last swing high/low (20-day) ──
        high_20d = round(float(high.iloc[-20:].max()), 2)
        low_20d = round(float(low.iloc[-20:].min()), 2)

        return {
            "sym": sym,
            "name": ticker.info.get("shortName", sym) if ticker.info else sym,
            "price": cur,
            "chg_pct": chg_pct,
            "chg_5d": chg_5d,
            "open": day_open,
            "high": day_high,
            "low": day_low,
            "rsi": rsi_now,
            "rsi_ma": rsi_ma,
            "rsi_zone": rsi_zone_name(rsi_now),
            "momentum": "↗️ Yükseliş" if rsi_now > rsi_ma else "↘️ Düşüş",
            "bb_mid": bb_mid_v,
            "bb_up": bb_up_v,
            "bb_lo": bb_lo_v,
            "bb_pos": bb_pos,
            "bb_note": bb_assessment(cur, bb_up_v, bb_lo_v, bb_mid_v),
            "sma_dist": sma_dist,
            "volume": vol_cur,
            "vol_ratio": vol_ratio,
            "high_20d": high_20d,
            "low_20d": low_20d,
        }

    except Exception as e:
        print(f"  [!] {sym} HATA: {e}")
        return None


# ─── REPORT FORMATTER ─────────────────────────────────

def format_report(results: list[dict]) -> str:
    now = datetime.utcnow()
    date_str = now.strftime("%d.%m.%Y")
    time_str = now.strftime("%H:%M UTC")

    lines = []
    lines.append(f"📊 <b>KUANTUM HİSSELERİ GÜNLÜK RAPOR</b>")
    lines.append(f"📅 {date_str} | ⏰ {time_str}")
    lines.append(f"{'─' * 32}")

    for r in results:
        if r is None:
            continue

        sym = r["sym"]
        name = r.get("name", sym)

        # Header
        arrow = "🔺" if r["chg_pct"] >= 0 else "🔻"
        lines.append(f"<b>{sym}</b> — {name}")
        lines.append(f"  💰 Fiyat: <b>${r['price']:.2f}</b> {arrow} %{r['chg_pct']:+.2f}")
        lines.append(f"  📈 Gün: A{r['open']:.2f} | Y{r['high']:.2f} | D{r['low']:.2f}")
        lines.append(f"  📉 5 Gün: %{r['chg_5d']:+.2f}")

        # RSI
        lines.append(f"  ── RSI (14) ──")
        lines.append(f"  RSI: <b>{r['rsi']:.1f}</b> → {r['rsi_zone']}")
        lines.append(f"  MA: {r['rsi_ma']:.1f} | Momentum: {r['momentum']}")

        # Bollinger
        lines.append(f"  ── Bollinger (20,2) ──")
        lines.append(f"  Üst: ${r['bb_up']:.2f} | Orta: ${r['bb_mid']:.2f} | Alt: ${r['bb_lo']:.2f}")
        lines.append(f"  Pozisyon: %{r['bb_pos']:.0f} | SMA20'den %{r['sma_dist']:+.1f}")
        lines.append(f"  Durum: {r['bb_note']}")

        # Volume
        vol_str = f"{r['volume']:,}".replace(",", ".")
        lines.append(f"  ── Hacim ──")
        lines.append(f"  {vol_str} ({r['vol_ratio']}x ort.)")

        # Key levels
        lines.append(f"  ── 20 Gün ──")
        lines.append(f"  Zirve: ${r['high_20d']:.2f} | Dip: ${r['low_20d']:.2f}")

        lines.append("")  # blank line between symbols

    # ── Summary Table ──
    lines.append(f"{'─' * 32}")
    lines.append("<b>📋 ÖZET TABLO</b>")
    lines.append(f"<pre>")
    header = f"{'Hisse':<6} {'Fiyat':>8} {'%Gün':>7} {'RSI':>6} {'Bölge':>12} {'SMA20%':>7}"
    lines.append(header)
    lines.append("-" * 52)

    for r in results:
        if r is None:
            continue
        rsi_short = "AŞIRI AL" if r["rsi"] >= 70 else ("AŞIRI SAT" if r["rsi"] <= 30 else "NÖTR")
        row = f"{r['sym']:<6} ${r['price']:>7.2f} {r['chg_pct']:>+6.2f}% {r['rsi']:>5.1f} {rsi_short:>12} {r['sma_dist']:>+6.1f}%"
        lines.append(row)

    lines.append("</pre>")

    # Signal
    lines.append(f"{'─' * 32}")
    signals = []
    for r in results:
        if r is None:
            continue
        if r["rsi"] >= 70:
            signals.append(f"⚠️ {r['sym']}: AŞIRI ALIM — satış fırsatı olabilir")
        elif r["rsi"] <= 30:
            signals.append(f"💡 {r['sym']}: AŞIRI SATIM — alım fırsatı olabilir")

    if signals:
        lines.append("<b>⚠️ SİNYALLER:</b>")
        for s in signals:
            lines.append(f"  {s}")
    else:
        lines.append("ℹ️ Bugün hiçbir hissede aşırı alım/satım sinyali yok.")

    lines.append(f"\n🤖 <i>Claude Code + yfinance + GitHub Actions</i>")

    return "\n".join(lines)


# ─── TELEGRAM SENDER ──────────────────────────────────

def send_telegram(text: str) -> bool:
    """Send message via Telegram Bot API with MarkdownV2 parsing disabled (HTML mode)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("HATA: TELEGRAM_BOT_TOKEN veya TELEGRAM_CHAT_ID ayarlanmamış!")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    # Split long messages (Telegram limit: 4096 chars)
    chunks = []
    remaining = text
    while len(remaining) > 0:
        if len(remaining) <= 4000:
            chunks.append(remaining)
            break
        # Find last newline before 4000
        split_at = remaining.rfind("\n", 0, 4000)
        if split_at == -1:
            split_at = 4000
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]

    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json()
            if not data.get("ok"):
                print(f"Telegram API hatası: {data}")
                return False
            print(f"  ✓ Telegram chunk {i+1}/{len(chunks)} gönderildi")
        except Exception as e:
            print(f"Telegram gönderme hatası: {e}")
            return False

    return True


# ─── ENTRY POINT ──────────────────────────────────────

def main():
    print("=" * 50)
    print("  KUANTUM HİSSELERİ GÜNLÜK ANALİZ")
    print(f"  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Semboller: {', '.join(SYMBOLS)}")
    print("=" * 50)

    if not TELEGRAM_BOT_TOKEN:
        print("\n⚠️  TELEGRAM_BOT_TOKEN ayarlanmamış!")
        print("   GitHub Secrets → TELEGRAM_BOT_TOKEN ekleyin")
    if not TELEGRAM_CHAT_ID:
        print("⚠️  TELEGRAM_CHAT_ID ayarlanmamış!")
        print("   GitHub Secrets → TELEGRAM_CHAT_ID ekleyin")

    results = []
    for sym in SYMBOLS:
        print(f"\n🔍 {sym} analiz ediliyor...")
        result = analyze_symbol(sym)
        if result:
            results.append(result)
            print(f"  ✓ {sym}: ${result['price']:.2f} | RSI {result['rsi']:.1f} | %{result['chg_pct']:+.2f}")
        else:
            print(f"  ✗ {sym}: Veri alınamadı")

    if not results:
        print("\n❌ Hiçbir hisse için veri alınamadı!")
        sys.exit(1)

    report = format_report(results)

    if DEBUG:
        print("\n" + "=" * 50)
        print("RAPOR (DEBUG modu):")
        print("=" * 50)
        print(report)

    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        print("\n📤 Telegram'a gönderiliyor...")
        if send_telegram(report):
            print("✅ Rapor gönderildi!")
        else:
            print("❌ Gönderim başarısız!")
            sys.exit(1)
    else:
        print("\n⚠️  Telegram yapılandırılmadı. Rapor gönderilemedi.")
        print("   Yukarıdaki çıktıyı inceleyin.")
        if not DEBUG:
            print(report)

    print("\n✨ Tamamlandı.")


if __name__ == "__main__":
    main()
