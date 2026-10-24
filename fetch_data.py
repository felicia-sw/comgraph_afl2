"""Download OSM layers for the Kali Jagir / Wonokromo study area once and save them locally.

Run: .venv/bin/python fetch_data.py
Output: data/*.geojson and data/jalan_walk.graphml (the notebook only reads these files).
"""
import time
from pathlib import Path

import osmnx as ox

ox.settings.use_cache = True
ox.settings.http_user_agent = "uc-computer-graphics-afl2"
ox.settings.requests_timeout = 180

# Study area around Jagir sluice gate, Wonokromo (left, bottom, right, top) in EPSG:4326
BBOX = (112.728, -7.312, 112.760, -7.292)
OUT = Path(__file__).parent / "data"
OUT.mkdir(exist_ok=True)

LAYERS = {
    "sungai": {"waterway": ["river", "canal"]},
    "badan_air": {"natural": "water", "water": ["river", "canal"]},
    "bangunan": {"building": True},
    "shelter": {"amenity": ["school", "university", "college", "townhall",
                            "place_of_worship", "community_centre"]},
}


def retry(fn, tries=5, wait=20):
    for k in range(tries):
        try:
            return fn()
        except Exception as e:  # server busy -> exponential backoff
            print(f"  attempt {k + 1} failed: {str(e)[:120]}")
            time.sleep(wait * 2 ** k)
    raise RuntimeError("Overpass still unavailable, try again later")


for name, tags in LAYERS.items():
    path = OUT / f"{name}.geojson"
    if path.exists():
        print("skip", name)
        continue
    print("download", name)
    gdf = retry(lambda: ox.features_from_bbox(BBOX, tags))
    keep = [c for c in ["name", "amenity", "building", "waterway", "natural", "water", "geometry"] if c in gdf]
    gdf.reset_index()[["element", "id"] + keep].to_file(path, driver="GeoJSON")
    print(f"  {len(gdf)} features")

g_path = OUT / "jalan_walk.graphml"
if not g_path.exists():
    print("download jalan (walk network)")
    G = retry(lambda: ox.graph_from_bbox(BBOX, network_type="walk"))
    ox.save_graphml(G, g_path)
    print(f"  {len(G.nodes)} nodes, {len(G.edges)} edges")
print("done")
