#!/usr/bin/env python3
"""
Quantum Decision Support Engine — Main Orchestrator   v0.3.0

Pipeline:
    symbols.yaml ──→ Data Layer ──→ Core (indicators, risk, scoring)
        ──→ JSON Generator ──→ Telegram Reporter

Usage:
    python analyze.py [--telegram] [--debug]

Environment:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID — for Telegram output
    POLYGON_API_KEY / ALPHA_VANTAGE_API_KEY — for production data sources

Exit codes:
    0 — success
    1 — fatal error (Sev1DataError or critical exception)
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
import yfinance as yf
import numpy as np
import pandas as pd

# ─── Project-level imports ───────────────────────────────
# (sys.path insert for local dev — GitHub Actions runs from repo root)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_providers.fallback_manager import DataFetcher
from data_providers.base import DailyData
from core.exceptions import DataError, Sev1DataError
from core.indicators import compute_all, sma, rsi, macd, atr
from core.gap_risk import calculate_g_worst
from core.position_sizing import calculate_position_size
from core.scoring import calculate_composite_score, score_to_regime, trend_label
from outputs.json_generator import generate_json, save_json, generate_batch_json
from outputs.telegram_reporter import build_report, send_report

# ─── Logging ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("quantum.engine")

# ─── Paths ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
CONFIG_DIR = ROOT / "config"
SYMBOLS_FILE = CONFIG_DIR / "symbols.yaml"
SETTINGS_FILE = CONFIG_DIR / "settings.yaml"
JSON_OUTPUT = ROOT / "outputs" / "analysis_data.json"


# ═══════════════════════════════════════════════════════════
# 1. CONFIG LOADER
# ═══════════════════════════════════════════════════════════

def load_config() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Read symbols and settings from YAML config files."""
    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        sym_cfg = yaml.safe_load(f) or {}

    with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
        set_cfg = yaml.safe_load(f) or {}

    active_symbols = [
        s for s in sym_cfg.get("symbols", []) if s.get("active", True)
    ]
    if not active_symbols:
        log.warning("No active symbols found in symbols.yaml")

    return active_symbols, set_cfg


# ═══════════════════════════════════════════════════════════
# 2. DATA LAYER
# ═══════════════════════════════════════════════════════════

def fetch_history_yfinance(symbol: str, period: str = "6mo") -> pd.DataFrame:
    """
    Fetch historical OHLCV for *symbol* via yfinance.

    This is the development-mode data source. In production, this function
    can be replaced by a ``DataFetcher``-based implementation that uses
    Polygon.io → Alpha Vantage with validated fallback.

    Returns a DataFrame with lowercase columns ``open, high, low, close, volume``.
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval="1d")

    if df.empty or len(df) < 30:
        raise ValueError(
            f"Insufficient data for {symbol}: "
            f"{'empty' if df.empty else f'{len(df)} bars (< 30)'}"
        )

    df.columns = [c.lower() for c in df.columns]
    return df


def fetch_production(symbol: str) -> pd.DataFrame:
    """
    Fetch data using the production provider chain (DataFetcher).

    NOTE: Currently a stub for architecture completeness. In production
    with Polygon/Alpha Vantage API keys configured, this would construct
    a DataFrame from DailyData objects for the last N days.
    """
    raise NotImplementedError(
        "Production data provider chain (Polygon → Alpha Vantage) "
        "requires API keys. Use yfinance fallback for now."
    )


# ═══════════════════════════════════════════════════════════
# 3. ANALYSE ONE SYMBOL
# ═══════════════════════════════════════════════════════════

def analyse_symbol(
    symbol: str,
    name: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """
    Full analysis pipeline for a single symbol.

    Args:
        symbol: Ticker (e.g. ``"QBTS"``).
        name: Human-readable company name.
        settings: Loaded settings dict.

    Returns:
        A dict with keys ``price``, ``indicators``, ``risk``, plus raw
        values required by ``json_generator`` and ``telegram_reporter``.
    """
    log.info("Analysing %s (%s) ...", symbol, name)

    # ── 3a. Data ─────────────────────────────────────
    try:
        df = fetch_history_yfinance(symbol)
    except ValueError as exc:
        log.error("Data fetch failed for %s: %s", symbol, exc)
        raise

    # ── 3b. Indicators ───────────────────────────────
    full = compute_all(df)
    last_idx = -1

    # Extract latest values into a flat dict
    ind: dict[str, Any] = {}

    # Price
    ind["price"] = float(df["close"].iloc[last_idx])
    ind["open"] = float(df["open"].iloc[last_idx])
    ind["high"] = float(df["high"].iloc[last_idx])
    ind["low"] = float(df["low"].iloc[last_idx])

    # Trend
    ind["sma_20"] = _safe_float(full, "sma_20", last_idx)
    ind["sma_50"] = _safe_float(full, "sma_50", last_idx)
    ind["vs_sma20_pct"] = _safe_float(full, "sma_20", last_idx)
    if ind["vs_sma20_pct"] is not None and ind["price"]:
        sma20_val = ind["vs_sma20_pct"]
        ind["vs_sma20_pct"] = round(
            (ind["price"] - sma20_val) / sma20_val * 100, 1
        )
    ind["macd"] = _safe_float(full, "macd", last_idx)
    ind["macd_signal"] = _safe_float(full, "macd_signal", last_idx)
    ind["macd_hist"] = _safe_float(full, "macd_hist", last_idx)
    ind["macd_bullish"] = bool(
        full["macd_bullish"].iloc[last_idx]
        if "macd_bullish" in full.columns
        else False
    )
    ind["adx"] = None  # requires manual ADX calc
    ind["trend_dir"] = None
    ind["adx_strength"] = None

    # Momentum
    ind["rsi"] = _safe_float(full, "rsi", last_idx)
    rsi_val = ind["rsi"]
    if rsi_val is not None:
        if rsi_val >= 70:
            ind["rsi_zone"] = "ASIRI ALIM"
        elif rsi_val <= 30:
            ind["rsi_zone"] = "ASIRI SATIM"
        elif rsi_val >= 60:
            ind["rsi_zone"] = "Yukselis"
        elif rsi_val <= 40:
            ind["rsi_zone"] = "Dusus"
        else:
            ind["rsi_zone"] = "Notr"
    else:
        ind["rsi_zone"] = "Bilinmiyor"

    # Volatility
    ind["atr"] = _safe_float(full, "atr", last_idx)
    atr_val = ind["atr"]
    ind["atr_pct"] = round(atr_val / ind["price"] * 100, 1) if atr_val and ind["price"] else None
    ind["bb_upper"] = None
    ind["bb_mid"] = ind.get("sma_20")  # BB middle = SMA20
    ind["bb_lower"] = None
    ind["bb_position"] = None
    ind["bb_squeeze"] = False

    # Volume
    ind["vol_last"] = int(df["volume"].iloc[last_idx])
    vol_avg5 = int(df["volume"].iloc[-6:-1].mean()) if len(df) >= 6 else ind["vol_last"]
    ind["vol_avg5"] = vol_avg5
    ind["vol_ratio"] = round(ind["vol_last"] / vol_avg5, 1) if vol_avg5 > 0 else 1.0

    # Levels
    high_20d = float(df["high"].iloc[-20:].max())
    low_20d = float(df["low"].iloc[-20:].min())
    close_price = ind["price"]
    pp = (close_price + float(df["high"].iloc[last_idx]) + float(df["low"].iloc[last_idx])) / 3
    ind["pivot"] = round(pp, 2)
    ind["r1"] = round(2 * pp - float(df["low"].iloc[last_idx]), 2)
    ind["s1"] = round(2 * pp - float(df["high"].iloc[last_idx]), 2)
    ind["r2"] = round(pp + (high_20d - low_20d), 2)
    ind["s2"] = round(pp - (high_20d - low_20d), 2)
    ind["high_20d"] = round(high_20d, 2)
    ind["low_20d"] = round(low_20d, 2)
    fib_r = high_20d - low_20d
    ind["fib_382"] = round(high_20d - 0.382 * fib_r, 2)
    ind["fib_618"] = round(high_20d - 0.618 * fib_r, 2)

    # ── 3c. Gap Risk ────────────────────────────────
    g_worst, gap_meta = calculate_g_worst(df)
    target_date = df.index[-1].strftime("%Y-%m-%d") if hasattr(df.index[-1], "strftime") else "unknown"

    # ── 3d. Position Sizing ─────────────────────────
    portfolio_value = float(os.environ.get("PORTFOLIO_VALUE", 10_000))
    r_max = portfolio_value * 0.01  # default: 1% risk per trade
    pos_result = calculate_position_size(
        r_max=r_max,
        g_worst=g_worst,
        portfolio_value=portfolio_value,
    )

    # ── 3e. Composite Score ────────────────────────
    score = calculate_composite_score(ind)

    # ── 3f. Labels ─────────────────────────────────
    regime_label, _ = score_to_regime(score)
    trend_lbl = trend_label(ind.get("macd_bullish"), ind.get("vs_sma20_pct"))

    # ── 3g. Price snapshot ─────────────────────────
    price_data = {
        "last": round(close_price, 2),
        "open": round(ind["open"], 2),
        "high": round(ind["high"], 2),
        "low": round(ind["low"], 2),
        "change_pct": round(
            (close_price - float(df["close"].iloc[-2])) / float(df["close"].iloc[-2]) * 100, 2
        ) if len(df) >= 2 else 0,
        "change_5d": round(
            (close_price - float(df["close"].iloc[-6])) / float(df["close"].iloc[-6]) * 100, 2
        ) if len(df) >= 6 else 0,
    }

    # ── Assemble ───────────────────────────────────
    return {
        "symbol": symbol,
        "name": name,
        "target_date": target_date,
        "price": price_data,
        "indicators": _nest_indicators(ind),
        "indicators_flat": ind,
        "gap_metadata": gap_meta,
        "risk": {
            "composite_score": score,
            "regime_label": regime_label,
            "trend_label": trend_lbl,
            "gap_risk_pct": round(g_worst * 100, 1),
            "max_position_pct": pos_result.get("position_size_pct", 0),
            "max_position_size": pos_result.get("position_size", 0),
            "position_capped": pos_result.get("capped", False),
            "cap_reason": pos_result.get("cap_reason", "mathematical"),
            "decision": (
                "Yeni alim sadece premarket kontrolunden sonra yapilabilir."
                if regime_label in ("Cok Yuksek Risk", "Yuksek Risk")
                else "Mevcut pozisyonlar korunabilir. Teyit beklenmeli."
            ),
        },
        "raw_score": {
            "g_worst": g_worst,
            "position_sizing": pos_result,
            "composite_score": score,
        },
    }


# ═══════════════════════════════════════════════════════════
# 4. HELPERS
# ═══════════════════════════════════════════════════════════

def _safe_float(df: pd.DataFrame, col: str, idx: int = -1) -> Optional[float]:
    """Extract a float from a DataFrame cell, returning None on failure."""
    if col not in df.columns:
        return None
    val = df[col].iloc[idx]
    if pd.isna(val):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _nest_indicators(flat: dict[str, Any]) -> dict[str, Any]:
    """Re-nest flat indicator dict into the structured format expected
    by ``json_generator`` and ``telegram_reporter``."""
    return {
        "trend": {
            "sma_20": flat.get("sma_20"),
            "sma_50": flat.get("sma_50"),
            "macd": flat.get("macd"),
            "macd_signal": flat.get("macd_signal"),
            "macd_hist": flat.get("macd_hist"),
            "macd_bullish": flat.get("macd_bullish"),
            "macd_signal_type": "bullish" if flat.get("macd_bullish") else "bearish",
            "adx": flat.get("adx"),
            "adx_strength": flat.get("adx_strength"),
        },
        "momentum": {
            "rsi": flat.get("rsi"),
            "rsi_zone": flat.get("rsi_zone", "Bilinmiyor"),
        },
        "volatility": {
            "atr": flat.get("atr"),
            "atr_pct": flat.get("atr_pct"),
            "bb_upper": flat.get("bb_upper"),
            "bb_mid": flat.get("bb_mid"),
            "bb_lower": flat.get("bb_lower"),
            "bb_position": flat.get("bb_position"),
            "bb_squeeze": flat.get("bb_squeeze", False),
        },
        "volume": {
            "last": flat.get("vol_last"),
            "avg_5d": flat.get("vol_avg5"),
            "ratio": flat.get("vol_ratio"),
        },
        "levels": {
            "pivot": flat.get("pivot"),
            "r1": flat.get("r1"),
            "s1": flat.get("s1"),
            "high_20d": flat.get("high_20d"),
            "low_20d": flat.get("low_20d"),
            "fib_382": flat.get("fib_382"),
            "fib_618": flat.get("fib_618"),
        },
    }


# ═══════════════════════════════════════════════════════════
# 5. TELEGRAM SUMMARY TABLE
# ═══════════════════════════════════════════════════════════

def build_summary_table(results: list[dict[str, Any]]) -> str:
    """ASCII summary table for the Telegram footer."""
    lines = [
        "<pre>",
        f"{'Hisse':<6} {'Fiyat':>8} {'%Gun':>7} {'RSI':>6} {'Skor':>5} {'Rejim':>16} {'Poz%':>6}",
        "-" * 58,
    ]
    for r in results:
        p = r["price"]
        ind = r["indicators_flat"]
        risk = r["risk"]
        regime = risk["regime_label"][:14]
        lines.append(
            f"{r['symbol']:<6} ${p['last']:>7.2f} {p['change_pct']:>+6.1f}% "
            f"{ind.get('rsi', 0):>5.0f} {risk['composite_score']:>4d} "
            f"{regime:>16} {risk['max_position_pct']:>5.1f}%"
        )
    lines.append("</pre>")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════
# 6. MAIN
# ═══════════════════════════════════════════════════════════

def main() -> int:
    flags = set(a for a in sys.argv[1:] if a.startswith("--"))
    send_tg = "--telegram" in flags
    debug = "--debug" in flags

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)

    log.info("=" * 48)
    log.info("  KUANTUM KARAR DESTEK MOTORU v0.3.0")
    log.info("  %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))
    log.info("=" * 48)

    # ── Load config ──────────────────────────────────
    try:
        symbols, settings = load_config()
    except Exception as exc:
        log.critical("Config yuklenemedi: %s", exc)
        _send_error_telegram(f"Config yuklenemedi: {exc}")
        return 1

    active = [s for s in symbols if s.get("active", True)]
    log.info("Semboller: %s", ", ".join(s["symbol"] for s in active))

    # ── Analyse each symbol ──────────────────────────
    results: list[dict[str, Any]] = []
    failed_count = 0

    for sym in active:
        ticker = sym["symbol"]
        name = sym.get("name", ticker)
        try:
            analysis = analyse_symbol(ticker, name, settings)
            results.append(analysis)
            risk = analysis["risk"]
            p = analysis["price"]
            log.info(
                "  OK %s $%.2f (%+.2f%%) | Skor %d/100 | Rejim: %s",
                ticker, p["last"], p["change_pct"],
                risk["composite_score"], risk["regime_label"],
            )
        except (DataError, ValueError, KeyError) as exc:
            failed_count += 1
            log.error("FAIL %s: %s", ticker, exc)
            if debug:
                traceback.print_exc()

    # ── Guard: all failed ────────────────────────────
    if not results:
        msg = "Hicbir sembol icin veri alinamadi. Rapor iptal."
        log.critical(msg)
        _send_error_telegram(msg)
        return 1

    # ── Generate JSON ────────────────────────────────
    json_docs = []
    for r in results:
        doc_id = generate_json(
            symbol=r["symbol"],
            price_data=r["price"],
            indicators=r["indicators_flat"],
            gap_risk={"g_worst": r["raw_score"]["g_worst"]},
            position_sizing=r["raw_score"]["position_sizing"],
            composite_score=r["risk"]["composite_score"],
            regime_label=r["risk"]["regime_label"],
            trend_label=r["risk"]["trend_label"],
            target_date=r["target_date"],
        )
        json_docs.append(doc_id)

    json_path = save_json(
        generate_batch_json(json_docs),
        filename="analysis_data.json",
    )
    log.info("JSON kaydedildi: %s", json_path)

    # ── Telegram Report ──────────────────────────────
    if send_tg:
        summary = build_summary_table(results)
        symbol_blocks = [
            (r["symbol"], r["name"], {
                "price": r["price"],
                "indicators": r["indicators"],
                "risk": r["risk"],
                "gap_metadata": r.get("gap_metadata", {}),
            })
            for r in results
        ]
        data_date = results[0].get("target_date", "unknown")
        report = build_report(symbol_blocks, summary_table=summary, data_date=data_date)

        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

        if not bot_token or not chat_id:
            log.warning("TELEGRAM_BOT_TOKEN/CHAT_ID ayarlanmamis — sadece JSON kaydedildi")
            if debug:
                print("\n" + report)
        else:
            ok = send_report(report, bot_token=bot_token, chat_id=chat_id)
            if ok:
                log.info("Telegram raporu GONDERILDI ✅")
            else:
                log.error("Telegram gonderimi BASARISIZ ❌")
                if not debug:
                    _send_error_telegram("Telegram raporu gonderilemedi.")
                return 1

    # ── Machine-readable JSON to stdout ──────────────
    summary_info = {
        "status": "success",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbols_analysed": len(results),
        "symbols_failed": failed_count,
        "json_path": json_path,
        "telegram_sent": send_tg,
    }
    print(json_summary := __import__("json").dumps(summary_info))
    log.info("OK — %d sembol analiz edildi, %d hata", len(results), failed_count)

    return 0


def _send_error_telegram(message: str) -> None:
    """Send a critical error notification to Telegram."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if bot_token and chat_id:
        import requests
        try:
            requests.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": f"🚨 <b>Sistem Hatasi</b>\n\n{message}\n\nRapor Iptal Edildi.",
                    "parse_mode": "HTML",
                },
                timeout=10,
            )
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
