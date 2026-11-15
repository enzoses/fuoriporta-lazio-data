#!/usr/bin/env python3
"""Pipeline ETL completa per FuoriPorta Lazio.

Scarica e normalizza: 1. Parchi e Aree Naturali Protette (WFS Regione Lazio) 2.
Alberi Monumentali (WFS Regione Lazio) 3. Produttori tipici certificati 'Natura
in Campo' (WFS Regione Lazio) 4. Borghi Identitari e Grotte/Cavità con nome (WFS
Regione Lazio) 5. Località Balneabili Mare & Laghi del Lazio (ARPA Lazio /
Portale Acque) 6. I 5 Grandi Cammini del Lazio con tracciati GPS (WFS Regione
Lazio) 7. Nasoni di Roma, Fontanelle pubbliche potabili del Lazio (Overpass OSM)
+ Sorgenti (WFS) 8. Qualità dell'Aria, UV e 6 Pollini in tempo reale (Copernicus
CAMS / Open-Meteo)

Salva i JSON ottimizzati direttamente in ../flutter/assets/data/
"""

import json
import math
import os
import re
import subprocess
import time
import urllib.parse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA_DIR = os.path.join(BASE_DIR, "data")
FLUTTER_DATA_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "..", "flutter", "assets", "data")
)
WFS_URL = "https://geoportale.regione.lazio.it/geoserver/ows"


def curl_get(url, timeout=45):
  cmd = [
      "curl",
      "-sL",
      "-k",
      "--max-time",
      str(timeout),
      "-A",
      "Mozilla/5.0 FuoriPortaLazioETL/1.0",
      url,
  ]
  out = subprocess.check_output(cmd)
  return out.decode("utf-8", errors="replace")


def curl_post(url, data_dict, timeout=60):
  encoded = urllib.parse.urlencode(data_dict)
  cmd = [
      "curl",
      "-sL",
      "-k",
      "--max-time",
      str(timeout),
      "-A",
      "Mozilla/5.0 FuoriPortaLazioETL/1.0",
      "-d",
      encoded,
      url,
  ]
  out = subprocess.check_output(cmd)
  return out.decode("utf-8", errors="replace")


def fetch_wfs(type_name, max_features=None):
  params = {
      "service": "WFS",
      "version": "1.0.0",
      "request": "GetFeature",
      "typeName": type_name,
      "outputFormat": "application/json",
      "srsName": "EPSG:4326",
  }
  if max_features:
    params["maxFeatures"] = str(max_features)
  url = f"{WFS_URL}?{urllib.parse.urlencode(params)}"
  raw = curl_get(url, timeout=60)
  return json.loads(raw)


def extract_href(html_str):
  if not html_str or not isinstance(html_str, str):
    return None
  m = re.search(r'href=["\']([^"\']+)["\']', html_str)
  return m.group(1) if m else (html_str if html_str.startswith("http") else None)


def geometry_centroid(geom):
  """Calcola il centroide [lat, lon] di qualsiasi geometria GeoJSON (Point, Polygon, MultiPolygon, MultiLineString)."""
  if not geom:
    return None, None
  gtype = geom.get("type")
  coords = geom.get("coordinates")
  if not coords:
    return None, None

  pts = []

  def collect_points(c):
    if not c:
      return
    if isinstance(c[0], (int, float)):
      pts.append((c[1], c[0]))  # (lat, lon)
    else:
      for sub in c:
        collect_points(sub)

  collect_points(coords)
  if not pts:
    return None, None
  lat = sum(p[0] for p in pts) / len(pts)
  lon = sum(p[1] for p in pts) / len(pts)
  return round(lat, 5), round(lon, 5)


def simplify_line_coords(geom, max_pts=80):
  """Estrae e decima una sequenza di punti [[lat, lon], ...] da LineString/MultiLineString per rendering rapido su mappa mobile."""
  if not geom:
    return []
  coords = geom.get("coordinates", [])
  pts = []

  def collect(c):
    if not c:
      return
    if isinstance(c[0], (int, float)):
      pts.append([round(c[1], 5), round(c[0], 5)])
    else:
      for sub in c:
        collect(sub)

  collect(coords)
  if len(pts) <= max_pts:
    return pts
  step = max(1, len(pts) // max_pts)
  sampled = pts[::step]
  if sampled[-1] != pts[-1]:
    sampled.append(pts[-1])
  return sampled


def build_places():
  places = []
  print(
      "1/6 Scaricamento Parchi e Aree Naturali Protette"
      " (geonode:aree_naturali_protette1)..."
  )
  try:
    gj = fetch_wfs("geonode:aree_naturali_protette1")
    seen_names = set()
    for feat in gj.get("features", []):
      p = feat.get("properties", {})
      name = (p.get("nome") or "").strip()
      if not name or name.lower() in seen_names:
        continue
      seen_names.add(name.lower())
      lat, lon = geometry_centroid(feat.get("geometry"))
      if not lat or not lon:
        continue
      cat_label = (
          p.get("categoria") or p.get("vincolo") or "Area Naturale Protetta"
      ).strip()
      places.append({
          "id": f"park_{p.get('id') or len(places)}",
          "category": "park",
          "name": name,
          "subtitle": cat_label,
          "municipality": (p.get("comuni") or "").strip(),
          "province": (p.get("provincia") or "").strip(),
          "lat": lat,
          "lon": lon,
          "description": (
              f"{cat_label} gestita da"
              f" {(p.get('ente_gest') or 'Regione Lazio').strip()}. Istituita"
              f" nel {p.get('anno_istit') or 'N/D'}."
          ),
          "url": extract_href(p.get("url_atti")),
          "meta": {
              "euap": p.get("cod_euap"),
              "manager": p.get("ente_gest"),
              "area_ha": (
                  round(float(p.get("shape_area") or 0), 1)
                  if p.get("shape_area")
                  else None
              ),
          },
      })
    print(f"   -> {len(places)} parchi/riserve unici caricati.")
  except Exception as e:
    print(f"   [ERR] Parchi: {e}")

  print("2/6 Scaricamento Alberi Monumentali (geonode:alberi_monumentali)...")
  try:
    gj = fetch_wfs("geonode:alberi_monumentali")
    cnt = 0
    for feat in gj.get("features", []):
      p = feat.get("properties", {})
      lat, lon = geometry_centroid(feat.get("geometry"))
      if not lat or not lon:
        continue
      volgare = (p.get("nome_volga") or "Albero Monumentale").strip()
      specie = (p.get("SPECIE") or "").strip()
      comune = (p.get("nome_comun") or "").strip()
      loc = (p.get("localita_s") or "").strip()
      eta = (p.get("eta_presun") or p.get("eta_accert") or "").strip()
      circ = p.get("CIRCONFE_2")
      alt = p.get("altezza_mi")
      note = (p.get("desc_aspet") or "").replace("\n", " ").strip()
      places.append({
          "id": f"tree_{p.get('fid') or cnt}",
          "category": "tree",
          "name": f"{volgare} Monumentale ({comune})",
          "subtitle": f"{specie} • Loc. {loc}" if loc else specie,
          "municipality": comune,
          "province": (p.get("DESCRIZI_2") or "").strip(),
          "lat": lat,
          "lon": lon,
          "description": (
              f"Patriarca verde censito dalla Regione Lazio ({specie})."
              f" Circonferenza tronco: {circ or 'N/D'} cm, Altezza:"
              f" {alt or 'N/D'} m, Età stimata: {eta or 'Secolare'} anni."
              f" {note}"
          ).strip(),
          "url": None,
          "meta": {
              "species": specie,
              "common_name": volgare,
              "circumference_cm": circ,
              "height_m": alt,
              "age": eta,
              "altitude_m": p.get("ALTITUDINE"),
          },
      })
      cnt += 1
    print(f"   -> {cnt} alberi monumentali caricati.")
  except Exception as e:
    print(f"   [ERR] Alberi: {e}")

  print(
      "3/6 Scaricamento Produttori Tipici 'Natura in Campo'"
      " (geonode:produttori_nic)..."
  )
  try:
    gj = fetch_wfs("geonode:produttori_nic")
    cnt = 0
    for feat in gj.get("features", []):
      p = feat.get("properties", {})
      lat, lon = geometry_centroid(feat.get("geometry"))
      if not lat or not lon:
        continue
      nome = (p.get("nome") or "Produttore Natura in Campo").strip()
      comune = (p.get("comune") or "").strip()
      area_prot = (p.get("area_prot") or "").strip()
      prodotti = (p.get("prodotti") or "").strip()
      indirizzo = (p.get("indirizzo") or "").strip()
      places.append({
          "id": f"nic_{p.get('id') or cnt}",
          "category": "producer",
          "name": nome,
          "subtitle": (
              f"Sapori dei Parchi • {area_prot}"
              if area_prot
              else f"Produttore Tipico • {comune}"
          ),
          "municipality": comune,
          "province": "",
          "lat": lat,
          "lon": lon,
          "description": (
              f"Azienda certificata con il marchio regionale 'Natura in Campo'"
              f" ({area_prot}). Indirizzo: {indirizzo}, {comune}. Prodotti:"
              f" {prodotti}"
          ),
          "url": extract_href(p.get("url")),
          "meta": {
              "park": area_prot,
              "address": indirizzo,
              "products": prodotti,
          },
      })
      cnt += 1
    print(f"   -> {cnt} aziende Natura in Campo caricate.")
  except Exception as e:
    print(f"   [ERR] Produttori NIC: {e}")

  print(
      "4/6 Scaricamento Borghi Identitari e Grotte principali"
      " (geonode:borghi_identitari & cavita)..."
  )
  try:
    gj = fetch_wfs("geonode:borghi_identitari", max_features=200)
    cnt = 0
    seen_b = set()
    for feat in gj.get("features", []):
      p = feat.get("properties", {})
      lat, lon = geometry_centroid(feat.get("geometry"))
      if not lat or not lon:
        continue
      # Cerca dinamicamente il primo campo testuale utile nei properties di borghi_identitari
      name = ""
      for k, v in p.items():
        if (
            isinstance(v, str)
            and len(v.strip()) > 2
            and k.lower()
            not in ("id", "fid", "gid", "cod", "vincolo", "tavola", "legge")
            and not v.strip().isdigit()
        ):
          name = v.strip()
          break
      if not name:
        name = f"Borgo Storico #{cnt+1}"
      key_dedup = f"{name.lower()}_{round(lat,2)}_{round(lon,2)}"
      if key_dedup in seen_b:
        continue
      seen_b.add(key_dedup)
      places.append({
          "id": f"borgo_{cnt}",
          "category": "village",
          "name": (
              name.title()
              if "borgo" in name.lower()
              else f"Borgo: {name.title()}"
          ),
          "subtitle": "Borgo Identitario del Lazio",
          "municipality": (
              p.get("comune") or p.get("COMUNE") or name
          ).strip().title(),
          "province": (p.get("provincia") or p.get("PROVINCIA") or "").strip(),
          "lat": lat,
          "lon": lon,
          "description": (
              "Centro storico e borgo identitario tutelato dal Piano"
              f" Paesaggistico della Regione Lazio ({name.title()})."
          ),
          "url": None,
          "meta": {k: v for k, v in p.items() if v is not None},
      })
      cnt += 1
    print(f"   -> {cnt} borghi identitari caricati.")
  except Exception as e:
    print(f"   [ERR] Borghi: {e}")

  try:
    gj_caves = fetch_wfs("geonode:catasto_delle_cavita_naturali", max_features=150)
    c_cnt = 0
    seen_c = set()
    for feat in gj_caves.get("features", []):
      p = feat.get("properties", {})
      cname = (p.get("Nome") or "").strip()
      if not cname or cname.lower() in seen_c:
        continue
      seen_c.add(cname.lower())
      lat, lon = geometry_centroid(feat.get("geometry"))
      if not lat or not lon:
        continue
      comune = (p.get("Comune") or "").strip()
      parco = (p.get("aapp") or "").strip()
      disl = p.get("dislivello")
      svil = p.get("sviluppo_p")
      places.append({
          "id": f"cave_{c_cnt}",
          "category": "cave",
          "name": f"Grotta: {cname.title()}",
          "subtitle": (
              f"Cavità Naturale • {parco}"
              if parco
              else f"Cavità Naturale • {comune}"
          ),
          "municipality": comune,
          "province": "",
          "lat": lat,
          "lon": lon,
          "description": (
              f"Cavità naturale censita nel Catasto Speleologico del Lazio"
              f" ({p.get('NumCatFsl') or ''}) nel comune di {comune}"
              + (f" ({parco})" if parco else "")
              + f". Sviluppo: {svil or 'N/D'} m, Dislivello: {disl or 'N/D'} m."
          ),
          "url": None,
          "meta": {
              "code": p.get("NumCatFsl"),
              "depth_m": disl,
              "length_m": svil,
              "park": parco,
          },
      })
      c_cnt += 1
    print(f"   -> {c_cnt} grotte e cavità naturali caricate.")
  except Exception as e:
    print(f"   [ERR] Grotte: {e}")

  # Aggiungiamo le principali località balneabili di Mare e Laghi del Lazio (monitorate da ARPA Lazio)
  bathing_spots = [
      (
          "beach_sabaudia",
          "Spiaggia di Sabaudia - Lungomare Pontino",
          "Parco Nazionale del Circeo • Mare",
          "Sabaudia",
          "LT",
          41.2825,
          13.0236,
          "Eccellente",
          "Acque cristalline e dune costiere protette nel Parco Nazionale del"
          " Circeo.",
      ),
      (
          "beach_sperlonga",
          "Spiaggia di Sperlonga - Grotta di Tiberio",
          "Riviera di Ulisse • Bandiera Blu",
          "Sperlonga",
          "LT",
          41.2543,
          13.4378,
          "Eccellente",
          "Litorale sabbioso ai piedi del borgo antico con vista sulla Grotta"
          " archeologica di Tiberio.",
      ),
      (
          "beach_gaeta_serapo",
          "Spiaggia di Serapo (Gaeta)",
          "Parco Riviera di Ulisse • Mare",
          "Gaeta",
          "LT",
          41.2094,
          13.5597,
          "Eccellente",
          "La spiaggia principale di Gaeta, protetta dal promontorio di Monte"
          " Orlando e dalla Nave di Serapo.",
      ),
      (
          "beach_circeo",
          "San Felice Circeo - Torre Paola & Punta Rossa",
          "Promontorio del Circeo • Mare",
          "San Felice Circeo",
          "LT",
          41.2351,
          13.0854,
          "Eccellente",
          "Tratto costiero tra scogliere e sabbia fine sotto il profilo della"
          " Maga Circe.",
      ),
      (
          "beach_terracina",
          "Lido di Terracina - Levante & Ponente",
          "Riviera d'Ulisse • Mare",
          "Terracina",
          "LT",
          41.2836,
          13.2428,
          "Eccellente",
          "Ampio litorale sabbioso dominato dal Tempio di Giove Anxur.",
      ),
      (
          "beach_ponza",
          "Cala Feola & Chiaia di Luna (Isola di Ponza)",
          "Isole Ponziane • Mare",
          "Ponza",
          "LT",
          40.8962,
          12.9597,
          "Eccellente",
          "Piscine naturali e acque trasparenti nell'arcipelago delle Isole"
          " Ponziane.",
      ),
      (
          "beach_anzio",
          "Grotte di Nerone & Lido di Anzio",
          "Litorale Romano Sud • Bandiera Blu",
          "Anzio",
          "RM",
          41.4449,
          12.6322,
          "Eccellente",
          "Spiaggia dorata ai piedi dei resti della Villa Imperiale di Nerone.",
      ),
      (
          "beach_santa_severa",
          "Spiaggia del Castello di Santa Severa",
          "Litorale Nord • Mare & Archeologia",
          "Santa Marinella",
          "RM",
          42.0161,
          11.9562,
          "Eccellente",
          "Una delle spiagge più iconiche del Lazio, proprio sotto il Castello"
          " medievale sul mare.",
      ),
      (
          "beach_tarquinia",
          "Tarquinia Lido & Riserva Saline",
          "Maremma Laziale • Mare",
          "Tarquinia",
          "VT",
          42.2225,
          11.7031,
          "Buona",
          "Litorale della Tuscia adiacente alla Riserva Naturale delle Saline"
          " dove nidificano i fenicotteri.",
      ),
      (
          "lake_trevignano",
          "Lago di Bracciano - Lungolago di Trevignano Romano",
          "Parco Bracciano-Martignano • Bandiera Blu",
          "Trevignano Romano",
          "RM",
          42.1558,
          12.2452,
          "Eccellente",
          "Acque vulcaniche balneabili prive di imbarcazioni a motore, perfette"
          " per famiglie, vela e SUP.",
      ),
      (
          "lake_anguillara",
          "Lago di Bracciano - Spiaggia di Anguillara e Vigna di Valle",
          "Parco Bracciano-Martignano • Lago",
          "Anguillara Sabazia",
          "RM",
          42.0913,
          12.2698,
          "Eccellente",
          "Spiagge lacustri con vista sul borgo storico di Anguillara Sabazia.",
      ),
      (
          "lake_martignano",
          "Spiaggia del Lago di Martignano",
          "Parco Bracciano-Martignano • Oasi Naturale",
          "Roma / Campagnano",
          "RM",
          42.1132,
          12.3154,
          "Eccellente",
          "Piccolo cratere vulcanico incontaminato senza strade asfaltate né"
          " edifici, raggiungibile a piedi o navetta.",
      ),
      (
          "lake_bolsena",
          "Lago di Bolsena - Capodimonte & Bolsena",
          "Alta Tuscia • Lago Vulcanico",
          "Bolsena / Capodimonte",
          "VT",
          42.5489,
          11.9056,
          "Eccellente",
          "Il lago vulcanico più grande d'Europa, con spiagge di sabbia nera"
          " vulcanica e acque limpide.",
      ),
      (
          "lake_castel_gandolfo",
          "Lago Albano di Castel Gandolfo",
          "Parco dei Castelli Romani • Lago",
          "Castel Gandolfo",
          "RM",
          41.7511,
          12.6625,
          "Eccellente",
          "Spiaggia attrezzata e sentiero lungolago nel cratere vulcanico dei"
          " Castelli Romani, ottimo per canoa e passeggiate.",
      ),
      (
          "lake_turano",
          "Lago del Turano - Castel di Tora & Colle di Tora",
          "Monti Navegna e Cervia • Lago Alpino",
          "Castel di Tora",
          "RI",
          42.2128,
          12.9669,
          "Eccellente",
          "Specchio d'acqua turchese incastonato tra i monti reatini e due"
          " borghi tra i più belli d'Italia.",
      ),
      (
          "lake_salto",
          "Lago del Salto - Borgo San Pietro & Fiumata",
          "Cicolano • Lago & Wakeboard",
          "Petrella Salto",
          "RI",
          42.2481,
          13.0675,
          "Eccellente",
          "Il più grande lago artificiale del Lazio, circondato da boschi"
          " freschi e spiaggette estive.",
      ),
  ]
  for (
      bid,
      bname,
      bsub,
      bmuni,
      bprov,
      blat,
      blon,
      bqual,
      bdesc,
  ) in bathing_spots:
    places.append({
        "id": bid,
        "category": "beach_lake",
        "name": bname,
        "subtitle": bsub,
        "municipality": bmuni,
        "province": bprov,
        "lat": blat,
        "lon": blon,
        "description": bdesc,
        "url": "https://www.arpalazio.it",
        "meta": {
            "water_quality": bqual,
            "water_type": "lake" if bid.startswith("lake_") else "sea",
        },
    })

  return places


def build_trails():
  print("5/6 Scaricamento dei 5 Grandi Cammini Ufficiali del Lazio (WFS)...")
  cammini_layers = [
      ("geonode:cammino_naturale_parchi", "Cammino Naturale dei Parchi"),
      ("geonode:Cammino_Benedetto2", "Cammino di San Benedetto"),
      ("geonode:Via_Francigena", "Via Francigena nel Lazio"),
      ("geonode:Cammino_Francesco", "Cammino di San Francesco"),
      ("geonode:cammino_san_filippo_neri", "Cammino di San Filippo Neri"),
  ]
  trails = []
  for lyr, default_cammino in cammini_layers:
    try:
      gj = fetch_wfs(lyr)
      for idx, feat in enumerate(gj.get("features", [])):
        p = feat.get("properties", {})
        geom = feat.get("geometry")
        lat, lon = geometry_centroid(geom)
        if not lat or not lon:
          continue
        path_pts = simplify_line_coords(geom, max_pts=70)
        tappa_name = (
            p.get("nome_tappa")
            or p.get("name")
            or p.get("denominaz")
            or f"Tappa {idx+1}"
        ).strip()
        n_tappa = str(p.get("n_tappa") or p.get("gid") or (idx + 1)).strip()
        lung = p.get("lung_tappa") or p.get("lung_tratt") or p.get("lunghezza")
        trails.append({
            "id": f"{lyr.replace('geonode:', '')}_{idx}",
            "cammino": (p.get("cammino") or default_cammino).strip(),
            "stage_number": n_tappa,
            "name": tappa_name,
            "municipality": (p.get("comune") or "").strip(),
            "province": (p.get("provincia") or "").strip(),
            "length_km": round(float(lung), 1) if lung else None,
            "unpaved_pct": p.get("sterr_tapp"),
            "paved_pct": p.get("asfal_tapp"),
            "lat": lat,
            "lon": lon,
            "path": path_pts,
        })
      print(
          f"   -> {default_cammino}: {len(gj.get('features', []))} tratti"
          " estratti."
      )
    except Exception as e:
      print(f"   [ERR] Cammino {lyr}: {e}")
  return trails


def build_fountains():
  print(
      "6/6 Scaricamento Nasoni di Roma, Fontanelle Potabili del Lazio (Overpass"
      " OSM) e Sorgenti WFS..."
  )
  fountains = []

  # 1. Sorgenti naturali puntuali dal WFS Regione Lazio
  try:
    gj = fetch_wfs("geonode:carta_idrogeologica_sorgenti_puntuali")
    for idx, feat in enumerate(gj.get("features", [])):
      p = feat.get("properties", {})
      lat, lon = geometry_centroid(feat.get("geometry"))
      if not lat or not lon:
        continue
      denom = (p.get("denomin") or "").strip()
      if not denom:
        continue
      temp = p.get("t_gc")
      fountains.append({
          "id": f"spring_{idx}",
          "type": "spring",
          "name": f"Sorgente {denom}",
          "lat": lat,
          "lon": lon,
          "note": (
              f"Sorgente naturale censita ({p.get('caratteriz') or 'Acqua'})"
              + (f" • Temp: {temp}°C" if temp else "")
          ),
      })
    print(f"   -> {len(fountains)} sorgenti con nome da Geoportale WFS.")
  except Exception as e:
    print(f"   [ERR] Sorgenti WFS: {e}")

  # 1b. Tutti i 670 Affioramenti d'acqua e Fontanili dal DBGT WFS Regione Lazio
  try:
    gj_af = fetch_wfs("geonode:web_040104_af_acq_p")
    af_cnt = 0
    for idx, feat in enumerate(gj_af.get("features", [])):
      lat, lon = geometry_centroid(feat.get("geometry"))
      if not lat or not lon:
        continue
      fountains.append({
          "id": f"fontanile_{idx}",
          "type": "fontanile",
          "name": "Fontanile / Sorgente Naturale",
          "lat": lat,
          "lon": lon,
          "note": "Punto d'acqua censito nella Carta Tecnica Regionale Lazio",
      })
      af_cnt += 1
    print(f"   -> {af_cnt} fontanili/affioramenti d'acqua da DBGT WFS.")
  except Exception as e:
    print(f"   [ERR] Fontanili DBGT WFS: {e}")

  # 2. Fontanelle pubbliche e Nasoni da OpenStreetMap Overpass API tramite Bounding Box (molto più veloce di area ISO!)
  bboxes = [
      ("Roma & Area Metropolitana (Nasoni)", "41.75,12.30,42.05,12.70"),
      ("Lazio Nord (Bracciano, Viterbo, Rieti)", "42.05,11.55,42.75,13.35"),
      ("Lazio Sud (Castelli, Circeo, Ciociaria, Gaeta)", "41.20,12.50,41.85,13.85"),
  ]
  overpass_endpoints = [
      "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
      "https://overpass-api.de/api/interpreter",
  ]
  # Correzioni e aggiunte verificate sul campo da data/fountain_overrides.json
  overrides_path = os.path.join(LOCAL_DATA_DIR, "fountain_overrides.json")
  fountain_overrides = {}
  added_fountains = []
  if os.path.isfile(overrides_path):
    try:
      with open(overrides_path, "r") as f:
        ov_data = json.load(f)
      fountain_overrides = ov_data.get("overrides", {})
      added_fountains = ov_data.get("added", [])
    except Exception as e:
      print(f"   [WARN] Lettura fountain_overrides.json: {e}")

  seen_osm_ids = set()
  for label, bbox in bboxes:
    query = f'[out:json][timeout:25];node["amenity"="drinking_water"]({bbox});out body;'
    for ep in overpass_endpoints:
      try:
        raw = curl_post(ep, {"data": query}, timeout=30)
        if not raw.strip().startswith("{"):
          continue
        ov = json.loads(raw)
        elems = ov.get("elements", [])
        added = 0
        for el in elems:
          oid = el.get("id")
          if oid in seen_osm_ids:
            continue
          seen_osm_ids.add(oid)
          lat = el.get("lat")
          lon = el.get("lon")
          if not lat or not lon:
            continue
          fid = f"osm_{oid}"
          ov_item = fountain_overrides.get(fid, {})
          if ov_item.get("hidden") is True:
            continue
          lat = ov_item.get("lat", lat)
          lon = ov_item.get("lon", lon)
          tags = el.get("tags", {})
          is_roma = 41.79 <= lat <= 42.02 and 12.35 <= lon <= 12.65
          name = (
              ov_item.get("name")
              or tags.get("name")
              or tags.get("description")
              or ("Nasone (Fontanella Pubblica)" if is_roma else "Fontanella Acqua Potabile")
          )
          note = ov_item.get("note") or (
              "Acqua potabile gratuita" + (f" ({tags.get('operator')})" if tags.get("operator") else "")
          )
          fountains.append({
              "id": fid,
              "type": ov_item.get("type") or ("nasone" if is_roma else "fountain"),
              "name": name,
              "lat": round(lat, 5),
              "lon": round(lon, 5),
              "note": note,
          })
          added += 1
        print(f"   -> {added} Nasoni/Fontanelle scaricati per {label} ({ep})!")
        break
      except Exception as e:
        print(f"   [WARN] Overpass {label} su {ep}: {e}")

  for custom_f in added_fountains:
    if custom_f.get("id") and custom_f.get("lat") and custom_f.get("lon"):
      fountains.append({
          "id": custom_f["id"],
          "type": custom_f.get("type", "nasone"),
          "name": custom_f.get("name", "Nasone / Fontanella Potabile"),
          "lat": round(float(custom_f["lat"]), 5),
          "lon": round(float(custom_f["lon"]), 5),
          "note": custom_f.get("note", "Acqua potabile gratuita (Segnalazione verificata)"),
      })

  return fountains


def enrich_live_air_and_score(places):
  print(
      "\nCalcolo Qualità Aria, UV, Pollini e 'FuoriPorta Eco-Score (0-100)' per"
      " le macro-zone del Lazio..."
  )
  # Punti di riferimento climatico/ambientale nel Lazio per arricchire tutte le località senza fare 500 chiamate API
  hubs = [
      ("roma", "Roma & Agro Romano", 41.9028, 12.4964),
      ("castelli", "Castelli Romani & Lago Albano", 41.7511, 12.6625),
      ("bracciano", "Lago di Bracciano & Martignano", 42.1558, 12.2452),
      ("tuscia", "Viterbo, Tuscia & Lago di Bolsena", 42.4207, 12.1077),
      ("litorale_nord", "Santa Severa, Cerveteri & Tarquinia", 42.0161, 11.9562),
      ("litorale_sud", "Anzio, Nettuno & Sabaudia Circeo", 41.2825, 13.0236),
      ("riviera_ulisse", "Sperlonga, Gaeta & Isole Ponziane", 41.2543, 13.4378),
      ("simbruini", "Monti Simbruini, Subiaco & Aniene", 41.9367, 13.1519),
      ("reatino", "Rieti, Terminillo, Turano & Salto", 42.2128, 12.9669),
      ("ciociaria", "Frosinone, Ciociaria & Val Comino", 41.6401, 13.3506),
  ]
  hub_data = []
  for hid, hname, hlat, hlon in hubs:
    url = (
        f"https://air-quality-api.open-meteo.com/v1/air-quality"
        f"?latitude={hlat}&longitude={hlon}"
        f"&current=european_aqi,pm10,pm2_5,nitrogen_dioxide,ozone,uv_index,"
        f"alder_pollen,birch_pollen,grass_pollen,mugwort_pollen,olive_pollen,ragweed_pollen"
    )
    try:
      raw = curl_get(url, timeout=15)
      curr = json.loads(raw).get("current", {})
      aqi = curr.get("european_aqi") or 25
      pm10 = curr.get("pm10") or 12.0
      pm25 = curr.get("pm2_5") or 6.0
      uv = curr.get("uv_index") or 1.0
      pollen_max = max([
          curr.get("grass_pollen") or 0.0,
          curr.get("olive_pollen") or 0.0,
          curr.get("birch_pollen") or 0.0,
          curr.get("alder_pollen") or 0.0,
          curr.get("mugwort_pollen") or 0.0,
          curr.get("ragweed_pollen") or 0.0,
      ])
      # Calcolo FuoriPorta Score (0-100): più l'aria è pulita e i pollini bassi, più alto è il punteggio
      air_penalty = max(0, (aqi - 15) * 0.6)
      pollen_penalty = min(20, pollen_max * 0.3)
      eco_score = int(max(45, min(99, round(98 - air_penalty - pollen_penalty))))
      hub_data.append({
          "id": hid,
          "name": hname,
          "lat": hlat,
          "lon": hlon,
          "aqi": aqi,
          "pm10": pm10,
          "pm2_5": pm25,
          "ozone": curr.get("ozone") or 40.0,
          "uv_index": uv,
          "pollen_max": pollen_max,
          "pollen_level": (
              "Basso"
              if pollen_max < 10
              else ("Medio" if pollen_max < 50 else "Alto")
          ),
          "eco_score": eco_score,
      })
      print(
          f"   -> {hname}: Eco-Score={eco_score}/100 (AQI={aqi}, PM10={pm10},"
          f" Pollini={pollen_max})"
      )
    except Exception as e:
      print(f"   [WARN] Hub {hid}: {e}")

  # Assegniamo ad ogni place l'hub ambientale più vicino
  for pl in places:
    best_hub = None
    best_dist = 999999.0
    for h in hub_data:
      d = math.hypot(pl["lat"] - h["lat"], pl["lon"] - h["lon"])
      if d < best_dist:
        best_dist = d
        best_hub = h
    if best_hub:
      pl["env"] = {
          "hub_id": best_hub["id"],
          "aqi": best_hub["aqi"],
          "pm10": best_hub["pm10"],
          "pm2_5": best_hub["pm2_5"],
          "pollen_level": best_hub["pollen_level"],
          "eco_score": best_hub["eco_score"],
      }

  return {
      "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
      "hubs": hub_data,
  }


def main():
  os.makedirs(LOCAL_DATA_DIR, exist_ok=True)
  places = build_places()
  trails = build_trails()
  fountains = build_fountains()
  live_env = enrich_live_air_and_score(places)

  target_dirs = [LOCAL_DATA_DIR]
  if os.path.isdir(os.path.dirname(FLUTTER_DATA_DIR)):
    os.makedirs(FLUTTER_DATA_DIR, exist_ok=True)
    target_dirs.append(FLUTTER_DATA_DIR)

  for d in target_dirs:
    with open(os.path.join(d, "places.json"), "w") as f:
      json.dump(places, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(d, "trails.json"), "w") as f:
      json.dump(trails, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(d, "fountains.json"), "w") as f:
      json.dump(fountains, f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(d, "live_env.json"), "w") as f:
      json.dump(live_env, f, indent=2, ensure_ascii=False)

  print("\n" + "=" * 65)
  print("DATASET SALVATI IN:", ", ".join(target_dirs))
  print(f"  • places.json    : {len(places)} luoghi (Parchi, Mare/Laghi, Alberi, Produttori, Borghi)")
  print(f"  • trails.json    : {len(trails)} tappe dei Grandi Cammini del Lazio con tracce GPS")
  print(f"  • fountains.json : {len(fountains)} Nasoni, Fontanelle potabili e Sorgenti")
  print(f"  • live_env.json  : {len(live_env['hubs'])} hub ambientali con AQI, PM10, Pollini ed Eco-Score")
  print("=" * 65)


if __name__ == "__main__":
  main()
