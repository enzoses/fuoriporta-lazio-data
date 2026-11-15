#!/usr/bin/env python3
"""Script di ispezione e sincronizzazione Open Data Regione Lazio per FuoriPorta Lazio.

Estrae i layer GeoJSON (EPSG:4326) dal Geoportale WFS e i dati qualità
aria/pollini.
"""

import json
import os
import ssl
import urllib.parse
import urllib.request

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) FuoriPortaLazioSync/1.0"
    )
}

WFS_BASE = "https://geoportale.regione.lazio.it/geoserver/ows"

CORE_WFS_LAYERS = [
    "geonode:aree_naturali_protette1",
    "geonode:alberi_monumentali",
    "geonode:produttori_nic",
    "geonode:cammino_naturale_parchi",
    "geonode:Cammino_Benedetto2",
    "geonode:Via_Francigena",
    "geonode:Cammino_Francesco",
    "geonode:cammino_san_filippo_neri",
    "geonode:borghi_identitari",
    "geonode:catasto_delle_cavita_naturali",
]


def fetch_json(url, timeout=25):
  req = urllib.request.Request(url, headers=HEADERS)
  with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
    return json.loads(resp.read().decode("utf-8", errors="replace"))


def download_wfs_layer(layer_name, max_features=None):
  params = {
      "service": "WFS",
      "version": "1.0.0",
      "request": "GetFeature",
      "typeName": layer_name,
      "outputFormat": "application/json",
      "srsName": "EPSG:4326",
  }
  if max_features:
    params["maxFeatures"] = str(max_features)
  url = f"{WFS_BASE}?{urllib.parse.urlencode(params)}"
  return fetch_json(url)


if __name__ == "__main__":
  out_dir = os.path.join(os.path.dirname(__file__), "output")
  os.makedirs(out_dir, exist_ok=True)
  for layer in CORE_WFS_LAYERS:
    print(f"Scaricamento sample WFS: {layer}...")
    try:
      data = download_wfs_layer(layer, max_features=5)
      safe_name = layer.replace("geonode:", "")
      with open(os.path.join(out_dir, f"{safe_name}_sample.json"), "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
      print(f"  [OK] Salvato {safe_name}_sample.json")
    except Exception as e:
      print(f"  [ERR] {layer}: {e}")
