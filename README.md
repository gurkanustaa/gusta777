# Premier League Predictor

Premier League maç verilerini otomatik olarak toplayıp PostgreSQL'e yüklemek ve daha sonra maç sonucu tahmin modeli geliştirmek için başlangıç projesi.

## Yaklaşım

İlk MVP için varsayılan geçmiş veri penceresi **100 gün**. Bu süre veri akışını doğrulamak, takımların son 5/10 maç formunu oluşturmak ve ilk modeli denemek için yeterli bir başlangıçtır. Model performansını sağlıklı ölçmek için sonraki aşamada aynı kodla 1-2 sezonluk geçmişe çıkabiliriz.

Örnek:

```bash
# Varsayılan: son 100 gün
python -m etl.load_matches

# Son 365 gün
python -m etl.load_matches --lookback-days 365

# Son 730 gün
python -m etl.load_matches --lookback-days 730
```

## İlk hedef

- İngiltere Premier League verilerini Sportmonks API v3 üzerinden çekmek
- İlk kurulumda varsayılan olarak son 100 günü yüklemek
- Daha uzun tarih aralıklarını otomatik parçalara bölmek
- Maç, takım, skor, maç istatistikleri ve varsa xG verisini PostgreSQL'e yazmak
- Aynı maç tekrar gelirse `UPSERT` ile güncellemek
- Airflow ile son maçları günlük otomatik yenilemek
- Son 5/10 maçtan leakage-safe model feature'ları üretmek

Premier League Sportmonks `league_id`: **8**.

Sportmonks fixture endpoint'i `participants`, `scores`, `statistics` ve `xGFixture` gibi include'ları destekler. Uygulama yalnızca ihtiyacımız olan bu ilişkileri ister ve pagination üzerinden tüm sonuçları toplar.

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
ETL_LOOKBACK_DAYS=100
ETL_CHUNK_DAYS=100
```

> `.env` Git'e gönderilmez.

## 2. PostgreSQL'i başlatma

Docker kullanıyorsanız:

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

Tarih vermeden çalıştırıldığında bugünden geriye varsayılan **100 gün** alınır:

```bash
python -m etl.load_matches
```

Belirli bir tarih aralığı:

```bash
python -m etl.load_matches --start-date 2026-06-06 --end-date 2026-09-13
```

Bir tam yıla çıkmak için:

```bash
python -m etl.load_matches --lookback-days 365
```

## 6. İlk model feature tablosunu üretme

ETL tamamlandıktan sonra:

```bash
python -m model.feature_engineering
```

Bu işlem PostgreSQL'de `ml_match_features` tablosunu oluşturur. Başlangıçta şu sinyaller bulunur:

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
- `fact_match_statistic`: Sportmonks fixture istatistikleri; tüm istatistik tipleri kaybolmadan tutulur
- `fact_match_xg`: takım bazlı xG ailesindeki metrikler
- `etl_run_log`: ETL çalışma geçmişi
- `ml_match_features`: model için türetilen geçmiş performans özellikleri

İstatistikleri sabit kolonlara erken aşamada zorlamak yerine `type_id/type_name/value` yapısında saklıyoruz. Böylece Sportmonks'tan gelen yeni istatistik türlerini veri kaybı olmadan tutabiliriz.

## Airflow

`airflow/premier_league_etl_dag.py` her gün saat 03:00'te son 14 günü yeniden çeker. Böylece yeni tamamlanan maçlar ve sonradan düzeltilen istatistikler güncellenir.

Airflow ortamında proje yolu farklıysa:

```env
GUSTA777_PROJECT_ROOT=/opt/airflow/gusta777
```

ayarlanabilir.

## Neden 100 günle başlıyoruz?

100 gün yaklaşık birkaç aylık güncel formu kapsar ve MVP için hızlı geri bildirim verir. Ancak nihai modelde yalnızca 100 günlük veriyle yetinmeyeceğiz. Backtest sonuçlarına göre 365 veya 730 güne çıkıp hangi pencerenin daha iyi `Log Loss`, `Brier Score` ve 1-X-2 doğruluğu verdiğini karşılaştıracağız.

## Sonraki aşama

Bir sonraki geliştirmede:

1. xG/xGA ve şut istatistiklerini feature tablosuna eklemek,
2. ELO rating hesaplamak,
3. zaman bazlı train/test ayrımı yapmak,
4. Poisson + XGBoost/LightGBM modellerini karşılaştırmak,
5. gelecek haftanın maçları için 1-X-2 olasılıklarını üretmek.
