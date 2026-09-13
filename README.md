# Premier League Predictor

Premier League maç verilerini otomatik olarak toplayıp PostgreSQL'e yüklemek ve daha sonra maç sonucu tahmin modeli geliştirmek için başlangıç projesi.

## Veri penceresi kararı

**100 gün**, veri akışını ve ETL'i hızlıca test etmek için kullanılabilir. Ancak 13 Eylül 2026 itibarıyla son 100 takvim gününün önemli bölümü Premier League yaz arasına denk geldiği için gerçek model eğitimi açısından yeterli değildir.

Bu nedenle varsayılan geçmiş pencereyi **365 gün** yaptık. Böylece önceki sezonun büyük bölümünü ve mevcut sezonun oynanan maçlarını birlikte kullanabiliriz. Daha sonra backtest sonuçlarına göre 730 güne de çıkabiliriz.

```bash
# Varsayılan: son 365 gün
python -m etl.load_matches

# Sadece hızlı ETL testi: son 100 gün
python -m etl.load_matches --lookback-days 100

# İki yıllık geçmiş
python -m etl.load_matches --lookback-days 730
```

## İlk hedef

- İngiltere Premier League verilerini Sportmonks API v3 üzerinden çekmek
- Varsayılan olarak son 365 günlük geçmişi yüklemek
- Uzun tarih aralıklarını 100 günlük parçalara bölmek
- Maç, takım, skor, maç istatistikleri ve varsa xG verisini PostgreSQL'e yazmak
- Aynı maç tekrar gelirse `UPSERT` ile güncellemek
- Airflow ile son maçları günlük otomatik yenilemek
- Son 5/10 maçtan leakage-safe model feature'ları üretmek

Premier League Sportmonks `league_id`: **8**.

## Proje yapısı

```text
.
├── airflow/
│   └── premier_league_etl_dag.py
├── database/
│   └── create_tables.sql
├── etl/
│   ├── __init__.py
│   ├── load_matches.py
│   └── sportmonks_api.py
├── model/
│   ├── __init__.py
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
SPORTMONKS_LEAGUE_ID=8
ETL_LOOKBACK_DAYS=365
ETL_CHUNK_DAYS=100
```

> `.env` Git'e gönderilmez. API token'ı public repository'ye commit etmeyin.

## 2. PostgreSQL'i başlatma

```bash
docker compose up -d postgres
```

Varsayılan bağlantı:

```text
postgresql://premier:premier@localhost:5432/premier_predictor
```

## 3. Python ortamı

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 4. Veritabanı tablolarını oluşturma

```bash
psql postgresql://premier:premier@localhost:5432/premier_predictor -f database/create_tables.sql
```

## 5. Premier League verisini yükleme

Varsayılan 365 gün:

```bash
python -m etl.load_matches
```

Belirli bir tarih aralığı:

```bash
python -m etl.load_matches --start-date 2025-09-13 --end-date 2026-09-13
```

ETL şu verileri ister:

- participants
- scores
- statistics + statistic type
- xGFixture + xG type

API sonuçları pagination ile tamamen okunur ve `fixtureLeagues:8` filtresiyle Premier League'e sınırlandırılır.

## 6. İlk model feature tablosunu üretme

```bash
python -m model.feature_engineering
```

Bu işlem PostgreSQL'de `ml_match_features` tablosunu oluşturur. Başlangıç feature'ları:

- Son 5 ve 10 maç puan ortalaması
- Son 5 ve 10 maç atılan gol ortalaması
- Son 5 ve 10 maç yenilen gol ortalaması
- Son 5 ve 10 maç gol farkı
- Son 5 ve 10 maç kazanma oranı
- 1 / X / 2 hedefi

Rolling değerler `shift(1)` sonrasında hesaplandığı için tahmin edilen maçın kendi sonucu feature hesaplamasına girmez.

## Veritabanı tabloları

- `dim_team`: takım bilgileri
- `fact_match`: maç ve skor bilgileri
- `fact_match_statistic`: tüm maç istatistikleri
- `fact_match_xg`: takım bazlı xG ailesindeki metrikler
- `etl_run_log`: ETL çalışma geçmişi
- `ml_match_features`: model için türetilmiş performans özellikleri

## Airflow

`airflow/premier_league_etl_dag.py` her gün saat 03:00'te son 14 günü yeniden çeker. Böylece yeni tamamlanan maçlar ve sonradan düzeltilen istatistikler güncellenir.

Airflow ortamında proje yolu farklıysa:

```env
GUSTA777_PROJECT_ROOT=/opt/airflow/gusta777
```

ayarlanabilir.

## Sonraki aşama

1. xG/xGA, şut ve topa sahip olma gibi istatistikleri model feature'larına eklemek
2. ELO rating hesaplamak
3. Zaman bazlı train/test ayrımı yapmak
4. Poisson + XGBoost/LightGBM modellerini karşılaştırmak
5. Gelecek haftanın maçları için 1-X-2 olasılıklarını üretmek
6. Log Loss, Brier Score ve kalibrasyon ile modeli ölçmek
