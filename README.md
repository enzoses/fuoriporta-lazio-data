# FuoriPorta Lazio — Open Data Feed (`fuoriporta-lazio-data`)

Dataset statici pre-elaborati e aggiornati automaticamente ogni 6 ore tramite **GitHub Actions** per l'app **FuoriPorta Lazio**.

## File JSON Esposti (`data/`)

- [`data/live_env.json`](data/live_env.json) — Qualità dell'Aria (`AQI`, `PM10`, `PM2.5`, `O3`), Indice UV, Pollini e *FuoriPorta Eco-Score (0–100)* per le 10 macro-aree del Lazio.
- [`data/places.json`](data/places.json) — **643 luoghi geolocalizzati** (119 Parchi/Riserve, 177 Alberi Monumentali, 139 Produttori *Natura in Campo*, 42 Borghi Identitari, 150 Grotte e 16 località Mare/Laghi balneabili).
- [`data/trails.json`](data/trails.json) — **246 tappe** dei 5 Grandi Cammini della Regione Lazio (*Via Francigena, Cammino di San Benedetto, Cammino Naturale dei Parchi, Cammino di San Francesco, Cammino di San Filippo Neri*) con tracciati GPS (`EPSG:4326`).
- [`data/fountains.json`](data/fountains.json) — **3.222 punti acqua potabile** (Nasoni di Roma, Fontanelle pubbliche potabili del Lazio e Sorgenti/Fontanili censiti).

## CDN Endpoints (jsDelivr)

- `https://cdn.jsdelivr.net/gh/enzoses/fuoriporta-lazio-data@main/data/live_env.json`
- `https://cdn.jsdelivr.net/gh/enzoses/fuoriporta-lazio-data@main/data/places.json`
- `https://cdn.jsdelivr.net/gh/enzoses/fuoriporta-lazio-data@main/data/trails.json`
- `https://cdn.jsdelivr.net/gh/enzoses/fuoriporta-lazio-data@main/data/fountains.json`

## Fonti e Licenze

- **Geoportale Regione Lazio / `dati.lazio.it` / ARPA Lazio** — Licenza **CC-BY 4.0** (L.R. Lazio 12/2016).
- **Copernicus Atmosphere Monitoring Service (CAMS) / Open-Meteo** — Licenza **CC-BY 4.0**.
- **OpenStreetMap Contributors (Punti Acqua Potabile)** — Licenza **ODbL**.
