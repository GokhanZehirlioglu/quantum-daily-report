# 🔧 Kuantum Hisseleri Günlük Rapor — Kurulum Rehberi

## Genel Bakış

Her iş günü **Almanya saatiyle 17:00'de** (ABD borsası açıldıktan 1.5 saat sonra) 
QBTS, RGTI, IONQ hisselerinin teknik analizini yapar ve **Telegram** mesajı olarak gönderir.

Tamamen **cloud tabanlıdır** — bilgisayarınızın açık olması gerekmez.

---

## 1. Telegram Bot Kurulumu (2 dakika)

### Adım 1: Bot Oluşturma
1. Telegram'da **@BotFather** hesabına gidin
2. `/newbot` yazın ve gönderin
3. Bot adını girin: `Kuantum Rapor`
4. Bot kullanıcı adı girin: `kuantum_rapor_bot` (unique olmalı)
5. Size bir **TOKEN** verecek — bunu saklayın!
   - Format: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### Adım 2: Chat ID'nizi Alın
1. Telegram'da **@userinfobot** hesabına gidin
2. `/start` yazın
3. Size **Your ID** değerini verecek — bunu saklayın!
   - Format: `123456789`

### Adım 3: Bot'u Başlatın
1. Oluşturduğunuz botun linkine gidin: `t.me/kuantum_rapor_bot`
2. **"START"** butonuna basın (bu önemli — bot size mesaj gönderebilmek için)

---

## 2. GitHub Kurulumu

### Adım 1: Repo Oluşturun
1. GitHub'a giriş yapın: https://github.com
2. **New Repository** → isim: `quantum-daily-report`
3. **Private** olarak işaretleyin (token'ları korumak için)
4. **Create repository**

### Adım 2: Secret'ları Ekleyin
1. Repo sayfasında **Settings → Secrets and variables → Actions**
2. **New repository secret** ile şunları ekleyin:

| Secret Adı | Değer |
|------------|-------|
| `TELEGRAM_BOT_TOKEN` | BotFather'dan aldığınız token |
| `TELEGRAM_CHAT_ID` | userinfobot'tan aldığınız ID |

### Adım 3: Kodu Yükleyin
```bash
cd C:\Users\Student\quantum-daily-report
git init
git add .
git commit -m "Kuantum hisseleri günlük rapor otomasyonu"
git branch -M main
git remote add origin https://github.com/KULLANICI_ADINIZ/quantum-daily-report.git
git push -u origin main
```

Push ettikten sonra GitHub Actions otomatik olarak test çalıştırması yapacak.

---

## 3. Test Etme

1. GitHub repo → **Actions** sekmesine gidin
2. **Quantum Stocks Daily Report** workflow'una tıklayın
3. **Run workflow** → **Run workflow** butonu ile manuel tetikleyin
4. Telegram'da raporu kontrol edin

---

## 4. Cron Ayarı

Varsayılan: Hafta içi her gün **15:00 UTC** (Almanya yaz saati 17:00)

**Kış saati için** (Ekim sonu — Mart sonu):
`.github/workflows/daily-report.yml` içinde cron satırını değiştirin:
```yaml
- cron: "0 16 * * 1-5"   # 16:00 UTC = 17:00 Almanya kış saati
```

---

## 📊 Örnek Rapor

```
📊 KUANTUM HİSSELERİ GÜNLÜK RAPOR
📅 11.06.2026 | ⏰ 15:00 UTC
────────────────────────────────

QBTS — D-Wave Quantum Inc.
  💰 Fiyat: $8.45 🔻 %-2.31
  📈 Gün: A8.62 | Y8.90 | D8.12
  📉 5 Gün: %-5.23
  ── RSI (14) ──
  RSI: 42.3 → 🟡 Aşağı yönlü
  MA: 55.1 | Momentum: ↘️ Düşüş
  ── Bollinger (20,2) ──
  Üst: $10.50 | Orta: $8.90 | Alt: $7.30
  Pozisyon: %35 | SMA20'den %-5.1
  Durum: Orta bandın altında (trend ↓)
  ...

📋 ÖZET TABLO
Hisse   Fiyat    %Gün   RSI       Bölge  SMA20%
QBTS   $8.45  -2.31%  42.3       NÖTR  -5.1%
RGTI  $19.45  -1.24%  45.1       NÖTR -11.2%
IONQ  $32.10  +1.50%  52.0       NÖTR  +2.3%

ℹ️ Bugün hiçbir hissede aşırı alım/satım sinyali yok.
```

---

## 🛠️ Yerel Test (Opsiyonel)

```bash
pip install -r requirements.txt
# .env dosyasını düzenleyin
python quantum_report.py
```
