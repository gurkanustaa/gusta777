# Premier League Predictor

Premier League maç verilerini otomatik olarak toplayıp PostgreSQL'e yüklemek ve daha sonra maç sonucu tahmin modeli geliştirmek için başlangıç projesi.

## İlk hedef

- İngiltere Premier League verilerini Sportmonks API v3 üzerinden çekmek
- Son 1 yıllık veriyi ilk yüklemede otomatik indirmek
- API'nin 100 günlük tarih aralığı limitini otomatik parçalara bölmek
- Maç, takım, skor, maç istatistikleri ve varsa xG verisini PostgreSQL'e yazmak
- Sonraki çalıştırmalarda sadece yeni/güncellenen maçları upsert etmek
- Airflow ile günlük otomatik güncelleme çalıştırmak

Premier League Sportmonks `league_id`: **8**.

## Proje yapısı

```text
.
├── airflow/
│   └── premier_league_etl_dag.py
├── database/
│   └── create_tables.sql
├── etl/
│   ├── load_matches.py
│   └── sportmonks_api.py
├── model/
│   └── feature_engineering.py
├── .env.example
├── .gitignore
├── docker-compose.yml
└── requirements.txt
```

## 1. Sportmonks API token

Sportmonks hesabından API token oluşturup `.env.example` dosyasını `.env` adıyla kopyalayın.

```bash
cp .env.example .env
```

`.env` içine gerçek token'ı yazın:

```env
SPORTMONKS_API_TOKEN=YOUR_TOKEN
```

> `.env` Git'e gönderilmez.

## 2. PostgreSQL'i başlatma

Docker kullanıyorsanız:

```bash
docker compose up -d postgres
```

Bu ayarla varsayılan bağlantı:

```text
postgresql://premier:premier@localhost:5432/premier_predictor
```

## 3. Python ortamı

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Veritabanı tabloları

```bash
psql postgresql://premier:premier@localhost:5432/premier_predictor -f database/create_tables.sql
```

## 5. Son 1 yıllık Premier League verisini yükleme

Tarih vermeden çalıştırıldığında bugünden geriye 365 gün çeker:

```bash
python -m etl.load_matches
```

Belirli bir tarih aralığı için:

```bash
python -m etl.load_matches --start-date 2025-09-13 --end-date 2026-09-13
```

## Veritabanı tabloları

- `dim_team`: takım bilgileri
- `fact_match`: maç ve skor bilgileri
- `fact_match_statistic`: Sportmonks fixture istatistikleri; tüm istatistik tipleri kaybolmadan tutulur
- `fact_match_xg`: paketiniz destekliyorsa takım bazlı xG
- `etl_run_log`: ETL çalışma geçmişi

İstatistikleri sabit kolonlara erken aşamada zorlamak yerine `type_id/type_name/value` yapısında tutuyoruz. Böylece Sportmonks'tan gelen yeni istatistik türlerini de veri kaybı olmadan saklayabiliriz.

## Sonraki aşama

`model/feature_engineering.py` üzerinden son 5/10 maç formu, iç saha/deplasman performansı, gol ortalamaları, xG/xGA ve ileride ELO gibi değişkenler üretilecek. Ardından Poisson + makine öğrenmesi modeli ile 1-X-2 olasılıkları hesaplanacak.
