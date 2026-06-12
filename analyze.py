#!/usr/bin/env python3
"""
Quantum Stocks Advanced Technical Analysis
===========================================
15+ indicators via pandas_ta — Trend, Momentum, Volatility, Volume, Levels
Usage: python analyze.py QBTS,RGTI,IONQ [--timeframe 1d] [--telegram]
"""

import yfinance as yf
import pandas as pd
import numpy as np
import json
import sys
import os
import requests
from datetime import datetime, timezone

# Try to import pandas_ta, fall back gracefully
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
    print("⚠️  pandas_ta not installed. Run: pip install pandas_ta", file=sys.stderr)

# ─── CONFIG ───────────────────────────────────────────
DEFAULT_SYMBOLS = ["QBTS", "RGTI", "IONQ"]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")


# ─── DATA FETCH ────────────────────────────────────────

def fetch_data(symbol: str, period: str = "3mo") -> pd.DataFrame | None:
    """Fetch OHLCV data and return DataFrame with proper column names."""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval="1d")
        if df.empty or len(df) < 30:
            return None
        # Standardize column names for pandas_ta
        df.columns = [c.lower() for c in df.columns]
        return df
    except Exception as e:
        print(f"  [!] {symbol}: fetch error — {e}", file=sys.stderr)
        return None


# ─── INDICATOR CALCULATIONS ────────────────────────────

def compute_indicators(df: pd.DataFrame) -> dict:
    """Compute all technical indicators and return structured dict."""
    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"]
    o = df["open"]

    result = {}
    last = close.iloc[-1]
    prev = close.iloc[-2]

    # ── Current price info ──
    result["price"] = {
        "last": round(float(last), 2),
        "open": round(float(o.iloc[-1]), 2),
        "high": round(float(high.iloc[-1]), 2),
        "low": round(float(low.iloc[-1]), 2),
        "change_pct": round(((last - prev) / prev) * 100, 2),
        "change_5d": round(((last - close.iloc[-6]) / close.iloc[-6]) * 100, 2) if len(close) >= 6 else 0,
        "change_20d": round(((last - close.iloc[-21]) / close.iloc[-21]) * 100, 2) if len(close) >= 21 else 0,
    }

    # ── Volume ──
    result["volume"] = {
        "last": int(vol.iloc[-1]),
        "avg_5d": int(vol.iloc[-6:-1].mean()) if len(vol) >= 6 else 0,
        "ratio": round(vol.iloc[-1] / vol.iloc[-6:-1].mean(), 1) if len(vol) >= 6 else 1.0,
    }

    if HAS_PANDAS_TA:
        try:
            # ── TREND ──
            sma20 = ta.sma(close, length=20)
            sma50 = ta.sma(close, length=50)
            sma200 = ta.sma(close, length=200)
            ema12 = ta.ema(close, length=12)
            ema26 = ta.ema(close, length=26)

            result["trend"] = {
                "sma20": round(float(sma20.iloc[-1]), 2) if pd.notna(sma20.iloc[-1]) else None,
                "sma50": round(float(sma50.iloc[-1]), 2) if pd.notna(sma50.iloc[-1]) else None,
                "sma200": round(float(sma200.iloc[-1]), 2) if pd.notna(sma200.iloc[-1]) else None,
                "ema12": round(float(ema12.iloc[-1]), 2) if pd.notna(ema12.iloc[-1]) else None,
                "ema26": round(float(ema26.iloc[-1]), 2) if pd.notna(ema26.iloc[-1]) else None,
                "price_vs_sma20": round(((last - sma20.iloc[-1]) / sma20.iloc[-1]) * 100, 1) if pd.notna(sma20.iloc[-1]) else None,
                "price_vs_sma50": round(((last - sma50.iloc[-1]) / sma50.iloc[-1]) * 100, 1) if pd.notna(sma50.iloc[-1]) else None,
                "ma_alignment": _ma_alignment(last, sma20.iloc[-1], sma50.iloc[-1], sma200.iloc[-1]),
            }

            # MACD
            macd_df = ta.macd(close, fast=12, slow=26, signal=9)
            if macd_df is not None:
                macd_val = macd_df.iloc[-1]
                result["trend"]["macd"] = round(float(macd_val["MACD_12_26_9"]), 3) if "MACD_12_26_9" in macd_val else None
                result["trend"]["macd_signal"] = round(float(macd_val["MACDs_12_26_9"]), 3) if "MACDs_12_26_9" in macd_val else None
                result["trend"]["macd_hist"] = round(float(macd_val["MACDh_12_26_9"]), 3) if "MACDh_12_26_9" in macd_val else None
                macd_line = result["trend"].get("macd", 0) or 0
                macd_sig = result["trend"].get("macd_signal", 0) or 0
                result["trend"]["macd_signal_type"] = "bullish" if macd_line > macd_sig else "bearish"

            # ADX — trend strength
            adx_df = ta.adx(high, low, close, length=14)
            if adx_df is not None:
                adx_val = adx_df.iloc[-1]
                result["trend"]["adx"] = round(float(adx_val["ADX_14"]), 1) if "ADX_14" in adx_val else None
                result["trend"]["dmi_plus"] = round(float(adx_val["DMP_14"]), 1) if "DMP_14" in adx_val else None
                result["trend"]["dmi_minus"] = round(float(adx_val["DMN_14"]), 1) if "DMN_14" in adx_val else None
                adx = result["trend"].get("adx", 0) or 0
                if adx > 40:
                    result["trend"]["trend_strength"] = "very_strong"
                elif adx > 25:
                    result["trend"]["trend_strength"] = "strong"
                elif adx > 20:
                    result["trend"]["trend_strength"] = "moderate"
                else:
                    result["trend"]["trend_strength"] = "weak"

            # ── MOMENTUM ──
            rsi = ta.rsi(close, length=14)
            stoch = ta.stoch(high, low, close, k=14, d=3)
            cci = ta.cci(high, low, close, length=20)

            result["momentum"] = {
                "rsi": round(float(rsi.iloc[-1]), 1) if pd.notna(rsi.iloc[-1]) else None,
                "rsi_zone": _rsi_zone(rsi.iloc[-1]),
            }

            if stoch is not None:
                result["momentum"]["stoch_k"] = round(float(stoch.iloc[-1]["STOCHk_14_3_3"]), 1) if "STOCHk_14_3_3" in stoch.iloc[-1] else None
                result["momentum"]["stoch_d"] = round(float(stoch.iloc[-1]["STOCHd_14_3_3"]), 1) if "STOCHd_14_3_3" in stoch.iloc[-1] else None

            result["momentum"]["cci"] = round(float(cci.iloc[-1]), 1) if pd.notna(cci.iloc[-1]) else None

            # ── VOLATILITY ──
            bb = ta.bbands(close, length=20, std=2)
            atr = ta.atr(high, low, close, length=14)

            result["volatility"] = {
                "atr": round(float(atr.iloc[-1]), 2) if pd.notna(atr.iloc[-1]) else None,
                "atr_pct": round((float(atr.iloc[-1]) / last) * 100, 1) if pd.notna(atr.iloc[-1]) else None,
            }

            if bb is not None:
                bb_last = bb.iloc[-1]
                bb_upper = float(bb_last["BBU_20_2.0"]) if "BBU_20_2.0" in bb_last else None
                bb_mid = float(bb_last["BBM_20_2.0"]) if "BBM_20_2.0" in bb_last else None
                bb_lower = float(bb_last["BBL_20_2.0"]) if "BBL_20_2.0" in bb_last else None
                result["volatility"]["bb_upper"] = round(bb_upper, 2) if bb_upper else None
                result["volatility"]["bb_mid"] = round(bb_mid, 2) if bb_mid else None
                result["volatility"]["bb_lower"] = round(bb_lower, 2) if bb_lower else None
                if bb_upper and bb_lower and (bb_upper - bb_lower) > 0:
                    result["volatility"]["bb_position_pct"] = round(((last - bb_lower) / (bb_upper - bb_lower)) * 100, 0)
                result["volatility"]["bb_squeeze"] = _bb_squeeze(df, close)

            # ── VOLUME INDICATORS ──
            try:
                obv = ta.obv(close, vol)
                result["volume"]["obv_trend"] = "up" if pd.notna(obv.iloc[-1]) and obv.iloc[-1] > obv.iloc[-6] else "down"
            except Exception:
                result["volume"]["obv_trend"] = None

        except Exception as e:
            result["_errors"] = result.get("_errors", []) + [f"pandas_ta error: {e}"]

    # ── SUPPORT / RESISTANCE (manual) ──
    last_20 = close.iloc[-20:]
    last_20_high = high.iloc[-20:]
    last_20_low = low.iloc[-20:]

    result["levels"] = {
        "high_20d": round(float(last_20_high.max()), 2),
        "low_20d": round(float(last_20_low.min()), 2),
        "high_5d": round(float(high.iloc[-5:].max()), 2),
        "low_5d": round(float(low.iloc[-5:].min()), 2),
        "pivot": round(float((high.iloc[-1] + low.iloc[-1] + close.iloc[-1]) / 3), 2),
    }

    # Resistance/Support from pivot
    pp = result["levels"]["pivot"]
    h = result["price"]["high"]
    l = result["price"]["low"]
    result["levels"]["r1"] = round(2 * pp - l, 2)
    result["levels"]["s1"] = round(2 * pp - h, 2)
    result["levels"]["r2"] = round(pp + (h - l), 2)
    result["levels"]["s2"] = round(pp - (h - l), 2)

    # Fibonacci from 20-day range
    fib_high = result["levels"]["high_20d"]
    fib_low = result["levels"]["low_20d"]
    fib_range = fib_high - fib_low
    result["levels"]["fib_382"] = round(fib_high - 0.382 * fib_range, 2)
    result["levels"]["fib_500"] = round(fib_high - 0.500 * fib_range, 2)
    result["levels"]["fib_618"] = round(fib_high - 0.618 * fib_range, 2)

    # ── SIGNALS ──
    result["signals"] = _detect_signals(result)

    return result


def _rsi_zone(rsi_val) -> str:
    if rsi_val is None or pd.isna(rsi_val):
        return "unknown"
    rsi_val = float(rsi_val)
    if rsi_val >= 70:
        return "overbought"
    elif rsi_val <= 30:
        return "oversold"
    elif rsi_val >= 60:
        return "bullish"
    elif rsi_val <= 40:
        return "bearish"
    return "neutral"


def _ma_alignment(price, sma20, sma50, sma200) -> str:
    """Determine MA alignment (bullish/bearish/mixed)."""
    if any(pd.isna(v) for v in [sma20, sma50, sma200]):
        return "unknown"
    if price > sma20 > sma50 > sma200:
        return "bullish_aligned"
    elif price < sma20 < sma50 < sma200:
        return "bearish_aligned"
    return "mixed"


def _bb_squeeze(df, close) -> bool | None:
    """Detect Bollinger Band squeeze (low volatility → breakout imminent)."""
    try:
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        bb_width = (2 * 2 * std20) / sma20
        current_width = bb_width.iloc[-1]
        avg_width = bb_width.iloc[-21:-1].mean()
        return current_width < avg_width * 0.85
    except Exception:
        return None


def _detect_signals(r: dict) -> list[str]:
    """Generate actionable signals from indicator data."""
    signals = []

    # RSI signals
    rsi = r.get("momentum", {}).get("rsi")
    if rsi and rsi >= 70:
        signals.append(f"RSI {rsi}: AŞIRI ALIM — satış sinyali")
    elif rsi and rsi <= 30:
        signals.append(f"RSI {rsi}: AŞIRI SATIM — alım sinyali")
    elif rsi and rsi <= 35:
        signals.append(f"RSI {rsi}: Aşırı satıma yaklaşıyor — izle")

    # MACD crossover
    macd = r.get("trend", {}).get("macd")
    macd_sig = r.get("trend", {}).get("macd_signal")
    macd_hist = r.get("trend", {}).get("macd_hist")
    if macd is not None and macd_sig is not None:
        if macd > macd_sig and macd_hist and macd_hist > 0:
            signals.append("MACD: Boğa crossover — yükseliş sinyali")
        elif macd < macd_sig and macd_hist and macd_hist < 0:
            signals.append("MACD: Ayı crossover — düşüş sinyali")

    # Bollinger squeeze
    if r.get("volatility", {}).get("bb_squeeze"):
        signals.append("BB Squeeze: Volatilite daralması — kırılım yakın olabilir")

    # BB position
    bb_pos = r.get("volatility", {}).get("bb_position_pct")
    if bb_pos is not None:
        if bb_pos <= 5:
            signals.append(f"BB: Alt bandda (%{bb_pos:.0f}) — potansiyel bounce")
        elif bb_pos >= 95:
            signals.append(f"BB: Üst bandda (%{bb_pos:.0f}) — potansiyel geri çekilme")

    # ADX
    trend_str = r.get("trend", {}).get("trend_strength")
    if trend_str == "very_strong":
        signals.append("ADX >40: Çok güçlü trend — trend yönünde işlem")

    # MA alignment
    ma = r.get("trend", {}).get("ma_alignment")
    if ma == "bearish_aligned":
        signals.append("MA dizilimi ayı — tüm SMA'lar fiyatın üstünde")
    elif ma == "bullish_aligned":
        signals.append("MA dizilimi boğa — tüm SMA'lar fiyatın altında")

    return signals


# ─── TELEGRAM FORMATTER ────────────────────────────────

def format_telegram_report(symbol: str, data: dict) -> str:
    """Format one symbol's analysis for Telegram HTML."""
    p = data["price"]
    tr = data.get("trend", {})
    mo = data.get("momentum", {})
    vo = data.get("volatility", {})
    vl = data.get("volume", {})
    lv = data.get("levels", {})
    sig = data.get("signals", [])

    arrow = "🔺" if p["change_pct"] >= 0 else "🔻"
    rsi_emoji = {"overbought": "🔴", "oversold": "🟢", "bullish": "🟠", "bearish": "🟡"}.get(
        mo.get("rsi_zone", ""), "⚪"
    )

    lines = []
    lines.append(f"<b>── {symbol} ──</b>")
    lines.append(f"💰 <b>${p['last']:.2f}</b> {arrow} %{p['change_pct']:+.2f}")
    lines.append(f"📈 Gün: A{p['open']:.2f} Y{p['high']:.2f} D{p['low']:.2f}")

    # Trend
    if tr:
        lines.append(f"📐 <b>Trend:</b> SMA20 ${tr.get('sma20','?')} | SMA50 ${tr.get('sma50','?')}")
        if tr.get("macd"):
            macd_type = tr.get("macd_signal_type", "")
            macd_arrow = "🟢" if macd_type == "bullish" else "🔴"
            lines.append(f"   MACD: {tr['macd']} (S:{tr.get('macd_signal','?')}) {macd_arrow}")
        adx = tr.get("adx", 0)
        if adx:
            strength_tr = {"very_strong": "🔥 Çok Güçlü", "strong": "💪 Güçlü", "moderate": "⚡ Orta", "weak": "😴 Zayıf"}
            lines.append(f"   ADX: {adx} — {strength_tr.get(tr.get('trend_strength',''), '?')}")

    # Momentum
    if mo:
        lines.append(f"🔄 <b>Momentum:</b> RSI {mo['rsi']} {rsi_emoji} ({_(mo.get('rsi_zone',''))})")
        if mo.get("stoch_k"):
            lines.append(f"   Stoch: %K {mo['stoch_k']} | %D {mo.get('stoch_d','?')}")

    # Volatility
    if vo:
        lines.append(f"📊 <b>Volatilite:</b> ATR ${vo.get('atr','?')} (%{vo.get('atr_pct','?')})")
        if vo.get("bb_mid"):
            bb_pos = vo.get("bb_position_pct", 50)
            lines.append(f"   BB: Ü${vo['bb_upper']} O${vo['bb_mid']} A${vo['bb_lower']} | Poz:%{bb_pos:.0f}")
            if vo.get("bb_squeeze"):
                lines.append("   ⚠️ BB Squeeze — kırılım yakın!")

    # Levels
    if lv:
        lines.append(f"🎯 <b>Seviyeler:</b> Pivot ${lv['pivot']} | R1 ${lv.get('r1','?')} | S1 ${lv.get('s1','?')}")
        lines.append(f"   Fib 38.2%: ${lv.get('fib_382','?')} | 61.8%: ${lv.get('fib_618','?')}")

    # Volume
    vol_ratio = vl.get("ratio", 1)
    vol_emoji = "🔥" if vol_ratio > 1.5 else ("😴" if vol_ratio < 0.5 else "📊")
    lines.append(f"📦 <b>Hacim:</b> {vl['last']:,} ({vol_ratio}x ort) {vol_emoji}".replace(",", "."))

    # Signals
    if sig:
        lines.append(f"")
        for s in sig:
            lines.append(f"⚠️ {s}")

    return "\n".join(lines)


def _ (en: str) -> str:
    """Translate indicator zones to Turkish."""
    return {
        "overbought": "AŞIRI ALIM",
        "oversold": "AŞIRI SATIM",
        "bullish": "Yükseliş eğilimi",
        "bearish": "Düşüş eğilimi",
        "neutral": "Nötr",
    }.get(en, en)


def format_summary_table(results: dict) -> str:
    """Create ASCII summary table."""
    lines = ["<pre>"]
    lines.append(f"{'Hisse':<6} {'Fiyat':>8} {'%Gün':>7} {'RSI':>6} {'ADX':>5} {'MACD':>6} {'BB%':>5} {'Sinyal'}")
    lines.append("-" * 70)
    for sym, data in results.items():
        if data is None:
            continue
        p = data["price"]
        tr = data.get("trend", {})
        mo = data.get("momentum", {})
        vo = data.get("volatility", {})
        sig_count = len(data.get("signals", []))
        sig_str = f"{'🔴' if sig_count > 0 else '⚪'} {sig_count}"
        lines.append(
            f"{sym:<6} ${p['last']:>7.2f} {p['change_pct']:>+6.1f}% "
            f"{mo.get('rsi',0):>5.1f} {tr.get('adx',0) or 0:>5.0f} "
            f"{'🟢' if tr.get('macd_signal_type')=='bullish' else '🔴':>6} "
            f"{vo.get('bb_position_pct',50):>4.0f}% {sig_str}"
        )
    lines.append("</pre>")
    return "\n".join(lines)


# ─── TELEGRAM SENDER ───────────────────────────────────

def send_telegram(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    # Split if too long
    for chunk in _chunk_text(text, 4000):
        try:
            resp = requests.post(url, json={
                "chat_id": TELEGRAM_CHAT, "text": chunk,
                "parse_mode": "HTML", "disable_web_page_preview": True
            }, timeout=15)
            if not resp.json().get("ok"):
                return False
        except Exception:
            return False
    return True


def _chunk_text(text: str, size: int):
    while len(text) > size:
        split = text.rfind("\n", 0, size)
        if split == -1:
            split = size
        yield text[:split]
        text = text[split:]
    yield text


# ─── MAIN ──────────────────────────────────────────────

def main():
    symbols = sys.argv[1].split(",") if len(sys.argv) > 1 else DEFAULT_SYMBOLS
    send_tg = "--telegram" in sys.argv

    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols": symbols,
        "analysis_start": True
    }, ensure_ascii=False))

    results = {}
    for sym in symbols:
        sym = sym.strip().upper()
        print(f"\n🔍 {sym}...", file=sys.stderr)
        df = fetch_data(sym)
        if df is None:
            print(f"  ✗ No data", file=sys.stderr)
            results[sym] = None
            continue

        data = compute_indicators(df)
        results[sym] = data
        sig_count = len(data.get("signals", []))
        rsi = data.get("momentum", {}).get("rsi", "?")
        print(f"  ✓ ${data['price']['last']} | RSI {rsi} | {sig_count} signals", file=sys.stderr)

    # Build full report
    now = datetime.now(timezone.utc)
    report_lines = [
        f"📊 <b>KUANTUM HİSSELERİ GÜNLÜK RAPOR</b>",
        f"📅 {now.strftime('%d.%m.%Y')} ⏰ {now.strftime('%H:%M UTC')}",
        f"",
    ]

    for sym in symbols:
        sym = sym.strip().upper()
        if results.get(sym):
            report_lines.append(format_telegram_report(sym, results[sym]))
            report_lines.append("")

    report_lines.append(format_summary_table(results))
    report_lines.append(f"🤖 Market Analyst Agent v0.1.0")

    report = "\n".join(report_lines)

    # Output
    if send_tg and TELEGRAM_TOKEN:
        print(f"\n📤 Telegram...", file=sys.stderr)
        ok = send_telegram(report)
        print(f"  {'✅' if ok else '❌'}", file=sys.stderr)

    # Also print JSON
    print(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": {s: r for s, r in results.items() if r is not None},
        "telegram_sent": send_tg and ok if send_tg else False,
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
