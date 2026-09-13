# GitHub Pages kurulumu

Bu proje statik web sitesini `docs/` klasöründen yayınlar.

## 1. Pages'i aç

GitHub repository > **Settings** > **Pages** bölümüne git.

- Source: **Deploy from a branch**
- Branch: **main**
- Folder: **/docs**
- Save

Yayın adresi: `https://gurkanustaa.github.io/gusta777/`

## 2. Sportmonks token'i Secret olarak ekle

Repository > **Settings** > **Secrets and variables** > **Actions** > **New repository secret**

Name:

`SPORTMONKS_API_TOKEN`

Value alanına Sportmonks API token'ını yaz.

Token hiçbir zaman `docs/`, `.env` veya başka bir public dosyaya yazılmamalıdır.

## 3. İlk veri güncellemesini çalıştır

Repository > **Actions** > **Update Premier League site data** > **Run workflow**.

Workflow gerçek Premier League verisini çekip `docs/data/site.json` dosyasını günceller. Sonraki güncellemeler her gün otomatik çalışır.

## Sayfalar

- Ana sayfa: `https://gurkanustaa.github.io/gusta777/`
- İstatistikler: `https://gurkanustaa.github.io/gusta777/statistics.html`

## Tahminler

İlk sürüm `Trend v0` modelidir. Son 10 maçtan form, gol ortalamaları ve ilk/ikinci yarı KG oranlarını kullanır. Bu geçici istatistik modelinin yerini daha sonra backtest edilmiş ML/Poisson ensemble modeli alacaktır.
