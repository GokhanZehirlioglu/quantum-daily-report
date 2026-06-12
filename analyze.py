#!/usr/bin/env python3
"""
Quantum Stocks Daily Technical Report
======================================
15+ indicators — pure numpy/pandas, no external TA libs
Works on Python 3.12+ and any environment

Usage:
  python analyze.py QBTS,RGTI,IONQ [--telegram]

Environment variables (for Telegram):
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import sys
import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import yfinance as yf
import requests

# ─── CONFIG ────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
SYMBOLS = ["QBTS", "RGTI", "IONQ"]

# ─── INDICATOR FUNCTIONS (manual, no dependencies) ─────────

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_g / avg_l.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_f = close.ewm(span=fast, adjust=False).mean()
    ema_s = close.ewm(span=slow, adjust=False).mean()
    macd_line = ema_f - ema_s
    sig_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - sig_line
    return macd_line, sig_line, hist


def _bbands(close: pd.Series, period=20, std=2):
    sma = close.rolling(period).mean()
    sd = close.rolling(period).std()
    return sma + std * sd, sma, sma - std * sd


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period=14):
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _stoch(high: pd.Series, low: pd.Series, close: pd.Series, k=14, d=3):
    ll = low.rolling(k).min()
    hh = high.rolling(k).max()
    sk = (close - ll) / (hh - ll) * 100
    sd = sk.rolling(d).mean()
    return sk, sd


def _cci(high: pd.Series, low: pd.Series, close: pd.Series, period=20):
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(period).mean()
    mad = tp.rolling(period).apply(lambda x: float(np.mean(np.abs(x - np.mean(x)))))
    return (tp - sma_tp) / (0.015 * mad)


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, period=14):
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    atr_val = tr.ewm(alpha=1 / period, adjust=False).mean()
    pdi = 100.0 * plus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val
    mdi = 100.0 * minus_dm.ewm(alpha=1 / period, adjust=False).mean() / atr_val
    dx = 100.0 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val, pdi, mdi


def _obv(close: pd.Series, volume: pd.Series):
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def _sma(series: pd.Series, period: int):
    return series.rolling(period).mean()


def _ema(series: pd.Series, period: int):
    return series.ewm(span=period, adjust=False).mean()


# ─── ZONE HELPERS ──────────────────────────────────────────

def rsi_zone(v):
    if v is None or np.isnan(v):
        return "unknown"
    if v >= 70:
        return "overbought"
    if v <= 30:
        return "oversold"
    if v >= 60:
        return "bullish"
    if v <= 40:
        return "bearish"
    return "neutral"


def adx_strength(v):
    if v is None or np.isnan(v):
        return "weak"
    if v > 40:
        return "very_strong"
    if v > 25:
        return "strong"
    if v > 20:
        return "moderate"
    return "weak"


# ─── ANALYZE ONE SYMBOL ────────────────────────────────────

def analyze_symbol(sym: str) -> dict | None:
    try:
        t = yf.Ticker(sym)
        df = t.history(period="3mo", interval="1d")
        if df.empty or len(df) < 30:
            return None

        c = df["Close"].astype(float)
        h = df["High"].astype(float)
        l = df["Low"].astype(float)
        o = df["Open"].astype(float)
        v = df["Volume"].astype(float)

        last = float(c.iloc[-1])
        prev = float(c.iloc[-2])

        # ── Price snapshot ──
        price = {
            "last": round(last, 2),
            "open": round(float(o.iloc[-1]), 2),
            "high": round(float(h.iloc[-1]), 2),
            "low": round(float(l.iloc[-1]), 2),
            "change_pct": round((last - prev) / prev * 100, 2),
            "change_5d": round((last - float(c.iloc[-6])) / float(c.iloc[-6]) * 100, 2) if len(c) >= 6 else 0.0,
        }

        # ── Volume ──
        v5 = v.iloc[-6:-1].mean()
        obv_series = _obv(c, v)
        volume = {
            "last": int(v.iloc[-1]),
            "avg_5d": int(v5),
            "ratio": round(float(v.iloc[-1]) / v5, 1) if v5 > 0 else 1.0,
            "obv_trend": "up" if float(obv_series.iloc[-1]) > float(obv_series.iloc[-6]) else "down",
        }

        # ── Trend ──
        s20 = _sma(c, 20)
        s50 = _sma(c, 50)
        e12 = _ema(c, 12)
        e26 = _ema(c, 26)
        ml, msig, mhist = _macd(c)
        ax, pdi, mdi = _adx(h, l, c)

        macd_v = float(ml.iloc[-1])
        macd_s = float(msig.iloc[-1])
        macd_h = float(mhist.iloc[-1])
        adx_v = float(ax.iloc[-1])

        trend = {
            "sma20": round(float(s20.iloc[-1]), 2),
            "sma50": round(float(s50.iloc[-1]), 2),
            "ema12": round(float(e12.iloc[-1]), 2),
            "ema26": round(float(e26.iloc[-1]), 2),
            "vs_sma20_pct": round((last - float(s20.iloc[-1])) / float(s20.iloc[-1]) * 100, 1),
            "macd": round(macd_v, 3),
            "macd_signal": round(macd_s, 3),
            "macd_hist": round(macd_h, 3),
            "macd_bullish": macd_v > macd_s,
            "adx": round(adx_v, 1),
            "adx_strength": adx_strength(adx_v),
            "trend_dir": "up" if float(pdi.iloc[-1]) > float(mdi.iloc[-1]) else "down",
        }

        # ── Momentum ──
        r = _rsi(c)
        sk, sd = _stoch(h, l, c)
        ci = _cci(h, l, c)

        rsi_v = float(r.iloc[-1])
        momentum = {
            "rsi": round(rsi_v, 1),
            "rsi_zone": rsi_zone(rsi_v),
            "stoch_k": round(float(sk.iloc[-1]), 1),
            "stoch_d": round(float(sd.iloc[-1]), 1),
            "cci": round(float(ci.iloc[-1]), 1),
        }

        # ── Volatility ──
        bu, bm, bl = _bbands(c)
        at = _atr(h, l, c)
        buv = float(bu.iloc[-1])
        blv = float(bl.iloc[-1])
        bmv = float(bm.iloc[-1])
        bb_width = (buv - blv)
        bb_pos = round((last - blv) / bb_width * 100, 0) if bb_width > 0 else 50.0

        # BB squeeze: current width < 85% of avg width
        bb_w_series = (bu - bl) / bm
        bb_sq = float(bb_w_series.iloc[-1]) < float(bb_w_series.iloc[-21:-1].mean()) * 0.85

        volatility = {
            "bb_upper": round(buv, 2),
            "bb_mid": round(bmv, 2),
            "bb_lower": round(blv, 2),
            "bb_position": bb_pos,
            "bb_squeeze": bool(bb_sq),
            "atr": round(float(at.iloc[-1]), 2),
            "atr_pct": round(float(at.iloc[-1]) / last * 100, 1),
        }

        # ── Levels ──
        h20 = float(h.iloc[-20:].max())
        l20 = float(l.iloc[-20:].min())
        pp = round((last + float(h.iloc[-1]) + float(l.iloc[-1])) / 3, 2)
        fib_r = h20 - l20

        levels = {
            "pivot": pp,
            "r1": round(2 * pp - float(l.iloc[-1]), 2),
            "s1": round(2 * pp - float(h.iloc[-1]), 2),
            "high_20d": round(h20, 2),
            "low_20d": round(l20, 2),
            "fib_382": round(h20 - 0.382 * fib_r, 2),
            "fib_500": round(h20 - 0.500 * fib_r, 2),
            "fib_618": round(h20 - 0.618 * fib_r, 2),
        }

        # ── Signals ──
        signals = []
        if rsi_v >= 70:
            signals.append(f"RSI {rsi_v:.0f}: ASIRI ALIM")
        elif rsi_v <= 30:
            signals.append(f"RSI {rsi_v:.0f}: ASIRI SATIM")
        elif rsi_v <= 35:
            signals.append(f"RSI {rsi_v:.0f}: Asiri satima yaklasma")
        if macd_v > macd_s and macd_h > 0:
            signals.append("MACD: Bullish crossover")
        elif macd_v < macd_s and macd_h < 0:
            signals.append("MACD: Bearish crossover")
        if bb_sq:
            signals.append(f"BB Squeeze: Volatilite daralmasi")
        if bb_pos <= 10:
            signals.append(f"BB: Alt banda yakin (%{bb_pos:.0f})")
        elif bb_pos >= 90:
            signals.append(f"BB: Ust banda yakin (%{bb_pos:.0f})")
        if adx_v > 40:
            signals.append(f"ADX {adx_v:.0f}: Cok guclu trend")
        if float(pdi.iloc[-1]) > float(mdi.iloc[-1]) * 2:
            signals.append("DMI: Guclu alis yonlu")
        elif float(mdi.iloc[-1]) > float(pdi.iloc[-1]) * 2:
            signals.append("DMI: Guclu satis yonlu")

        return {
            "symbol": sym,
            "price": price,
            "trend": trend,
            "momentum": momentum,
            "volatility": volatility,
            "volume": volume,
            "levels": levels,
            "signals": signals,
        }

    except Exception as e:
        print(f"  [!] {sym} HATA: {e}", file=sys.stderr)
        return None


# ─── TELEGRAM FORMAT ──────────────────────────────────────

ZONE_LABELS = {
    "overbought": "ASIRI ALIM", "oversold": "ASIRI SATIM",
    "bullish": "Yukselis", "bearish": "Dusus", "neutral": "Notr",
}
ZONE_EMOJI = {
    "overbought": "🔴", "oversold": "🟢", "bullish": "🟠",
    "bearish": "🟡", "neutral": "⚪",
}
ADX_EMOJI = {
    "very_strong": "🔥", "strong": "💪", "moderate": "⚡", "weak": "😴",
}


def format_symbol(d: dict) -> str:
    p = d["price"]
    tr = d["trend"]
    mo = d["momentum"]
    vo = d["volatility"]
    vl = d["volume"]
    lv = d["levels"]
    sig = d["signals"]

    arrow = "🔺" if p["change_pct"] >= 0 else "🔻"
    lines = [
        f"<b>── {d['symbol']} ──</b>",
        f"💰 <b>${p['last']}</b> {arrow} %{p['change_pct']:+.2f}",
        f"📈 A{p['open']} Y{p['high']} D{p['low']} | 5G %{p['change_5d']:+.2f}",
        f"",
        f"📐 <b>TREMD:</b>",
        f"   SMA20: ${tr['sma20']} | SMA50: ${tr['sma50']} | Fiyat %{tr['vs_sma20_pct']:+.1f}",
        f"   MACD: {tr['macd']} / S:{tr['macd_signal']} {'🟢' if tr['macd_bullish'] else '🔴'}",
        f"   ADX: {tr['adx']} {ADX_EMOJI.get(tr['adx_strength'],'')} | Yon: {'Yukselis' if tr['trend_dir'] == 'up' else 'Dusus'}",
        f"",
        f"🔄 <b>MOMENTUM:</b>",
        f"   RSI(14): {mo['rsi']} {ZONE_EMOJI.get(mo['rsi_zone'],'')} ({ZONE_LABELS.get(mo['rsi_zone'],'?')})",
        f"   Stoch: %K {mo['stoch_k']} | %D {mo['stoch_d']} | CCI: {mo['cci']}",
        f"",
        f"📊 <b>VOLATILITE:</b>",
        f"   BB: U${vo['bb_upper']} | O${vo['bb_mid']} | A${vo['bb_lower']} | Poz:%{vo['bb_position']:.0f}",
        f"   ATR: ${vo['atr']} (%{vo['atr_pct']}){' ⚠️ SQUEEZE' if vo['bb_squeeze'] else ''}",
        f"",
        f"📦 <b>HACIM:</b> {vl['last']:,} ({vl['ratio']}x ort) | OBV:{vl['obv_trend']}".replace(",", "."),
        f"",
        f"🎯 <b>SEVIYELER:</b>",
        f"   Pivot ${lv['pivot']} | R1 ${lv['r1']} | S1 ${lv['s1']}",
        f"   Fib 38% ${lv['fib_382']} | 50% ${lv['fib_500']} | 62% ${lv['fib_618']}",
        f"   20G Zirve: ${lv['high_20d']} | Dip: ${lv['low_20d']}",
    ]

    if sig:
        lines.append("")
        lines.append("⚠️ <b>SINYALLER:</b>")
        for s in sig:
            lines.append(f"  ⚠️ {s}")

    return "\n".join(lines)


def format_table(valid: dict) -> str:
    lines = [
        "<pre>",
        f"{'Hisse':<6} {'Fiyat':>8} {'%Gun':>7} {'RSI':>6} {'ADX':>5} {'MACD':>7} {'BB%':>5} {'Sinyal'}",
        "-" * 62,
    ]
    for sym, d in valid.items():
        p = d["price"]
        tr = d["trend"]
        mo = d["momentum"]
        vo = d["volatility"]
        sc = len(d["signals"])
        macd_icon = "🟢Bull" if tr["macd_bullish"] else "🔴Bear"
        lines.append(
            f"{sym:<6} ${p['last']:>7.2f} {p['change_pct']:>+6.1f}% "
            f"{mo['rsi']:>5.1f} {tr['adx']:>5.0f} {macd_icon:>7} "
            f"{vo['bb_position']:>4.0f}% {sc}"
        )
    lines.append("</pre>")
    return "\n".join(lines)


# ─── TELEGRAM SENDER ──────────────────────────────────────

def send_tg(text: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT:
        return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for part in _chunk(text, 4000):
        try:
            r = requests.post(url, json={
                "chat_id": TELEGRAM_CHAT,
                "text": part,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            }, timeout=15)
            if not r.json().get("ok"):
                return False
        except Exception:
            return False
    return True


def _chunk(text: str, size: int):
    while len(text) > size:
        split = text.rfind("\n", 0, size)
        if split == -1:
            split = size
        yield text[:split]
        text = text[split:]
    yield text


# ─── MAIN ──────────────────────────────────────────────────

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    symbols = [s.strip().upper() for s in args[0].split(",")] if args else SYMBOLS
    send_flag = "--telegram" in flags

    now = datetime.now(timezone.utc)
    print(f"KUANTUM ANALIZ — {now.strftime('%d.%m.%Y %H:%M UTC')}", file=sys.stderr)
    print(f"Semboller: {', '.join(symbols)}", file=sys.stderr)

    results = {}
    for sym in symbols:
        print(f"\n{sym}...", file=sys.stderr)
        d = analyze_symbol(sym)
        results[sym] = d
        if d:
            print(f"  -> ${d['price']['last']} | RSI {d['momentum']['rsi']} | {len(d['signals'])} sinyal", file=sys.stderr)
        else:
            print(f"  -> HATA", file=sys.stderr)

    valid = {s: d for s, d in results.items() if d}
    if not valid:
        print("Hic veri alinamadi!", file=sys.stderr)
        sys.exit(1)

    # Build report
    report_parts = [
        f"📊 <b>KUANTUM HISSE GUNLUK RAPOR</b>",
        f"📅 {now.strftime('%d.%m.%Y')} ⏰ {now.strftime('%H:%M UTC')}",
        "",
    ]
    for sym in symbols:
        if sym in valid:
            report_parts.append(format_symbol(valid[sym]))
            report_parts.append("───")

    report_parts.append("")
    report_parts.append("<b>📋 TABLO</b>")
    report_parts.append(format_table(valid))

    total_sig = sum(len(d["signals"]) for d in valid.values())
    if total_sig > 0:
        report_parts.append(f"\n<b>⚠️ {total_sig} sinyal!</b>")

    report_parts.append(f"\n🤖 Market Analyst | {now.strftime('%d.%m.%Y %H:%M')}")
    report = "\n".join(report_parts)

    # Output
    if send_flag:
        print("\nTelegram...", file=sys.stderr)
        if send_tg(report):
            print("GONDERILDI ✅", file=sys.stderr)
        else:
            print("HATA ❌", file=sys.stderr)
    else:
        print("\n" + report)

    # Check what went wrong in GitHub
    if not send_flag and not TELEGRAM_TOKEN:
        print("\nNot: TELEGRAM_BOT_TOKEN ayarlanmamis.", file=sys.stderr)

    return valid


if __name__ == "__main__":
    main()
