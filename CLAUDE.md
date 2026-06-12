# Quantum Daily Report — Trading Agent

## Tek Yapı
Bu repo iki sistemi birden içerir:

### 1. ☁️ Cloud Otomasyon (GitHub Actions)
- `analyze.py` — 15+ indikatörlü teknik analiz
- `.github/workflows/daily-report.yml` — Her gün 17:00 Almanya
- Telegram @Kuatum_Rapor_Bot
- Bilgisayar kapalıyken çalışır

### 2. 🤖 Claude Code Agent (CLI'da manuel)
- `agents/market-analyst.md` — Derinlemesine analiz agent'ı
- `skills/technical-analysis/` — Detaylı skill referansı
- `config/symbols.yaml` — Portföy konfigürasyonu
- TradingView MCP ile zenginleştirilebilir

## Semboller
QBTS, RGTI, IONQ

## Çalıştırma
```bash
python analyze.py QBTS,RGTI,IONQ       # konsola yazdırır
python analyze.py QBTS,RGTI,IONQ --telegram  # Telegram'a gönderir
```

## Agent Kullanımı
"piyasa analizi yap" veya "teknik rapor hazırla" dediğinde market-analyst agent'ı devreye girer.
