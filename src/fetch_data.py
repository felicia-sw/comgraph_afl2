import os
import time
import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely.geometry import box

# Konfigurasi OSMnx
ox.settings.use_cache = True
ox.settings.log_console = True
ox.settings.timeout = 180

# 1. DEFINISI PARAMETER AREA STUDI (Sesuai Proposal Bab 1.2)
# Core BBox: 112.728 - 112.760 BT (West - East), 7.292 - 7.312 LS (North - South)
WEST, SOUTH, EAST, NORTH = 112.728, -7.312, 112.760, -7.292
PADDING_METERS = 500  # Tambahan jarak pinggir 500 m

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)


def get_padded_bbox():
    """Membuat bounding box area inti dan area + 500m padding dalam EPSG:4326."""
    core_poly = box(WEST, SOUTH, EAST, NORTH)
    core_gdf = gpd.GeoDataFrame({"id": ["core"]}, geometry=[core_poly], crs="EPSG:4326")
    
    # Simpan batas area inti untuk dipakai pemotongan (clipping) di load_layers()
    core_file = os.path.join(DATA_DIR, "core_bbox.geojson")
    if not os.path.exists(core_file):
        core_gdf.to_file(core_file, driver="GeoJSON")

    # Transform ke EPSG:32749 (meter) untuk tambah jarak pinggir 500 m
    padded_utm = core_gdf.to_crs("EPSG:32749").buffer(PADDING_METERS)
    padded_wgs84 = padded_utm.to_crs("EPSG:4326")

    # Ambil bounds: (minx/west, miny/south, maxx/east, maxy/north)
    w, s, e, n = padded_wgs84.total_bounds
    return (w, s, e, n)


def fetch_osm_features(bbox_tuple, tags):
    """Helper kompatibel untuk OSMnx v2.0+ maupun v1.x."""
    w, s, e, n = bbox_tuple
    try:
        # OSMnx >= 2.0 menggunakan urutan (left/west, bottom/south, right/east, top/north)
        return ox.features_from_bbox(bbox=(w, s, e, n), tags=tags)
    except TypeError:
        # Fallback jika menggunakan OSMnx < 2.0 (north, south, east, west)
        return ox.features_from_bbox(north=n, south=s, east=e, west=w, tags=tags)


def fetch_osm_graph(bbox_tuple, network_type="walk"):
    """Helper download graph kompatibel untuk OSMnx v2.0+ maupun v1.x."""
    w, s, e, n = bbox_tuple
    try:
        return ox.graph_from_bbox(bbox=(w, s, e, n), network_type=network_type)
    except TypeError:
        return ox.graph_from_bbox(north=n, south=s, east=e, west=w, network_type=network_type)


def clean_columns_for_geojson(gdf, keep_cols):
    """Membersihkan tipe data list/dict dari OSM agar tidak error saat disimpan ke GeoJSON."""
    gdf = gdf.reset_index()
    available_cols = [c for c in keep_cols if c in gdf.columns]
    gdf = gdf[available_cols + ["geometry"]].copy()
    for col in available_cols:
        gdf[col] = gdf[col].astype(str).replace("nan", None)
    return gdf


def main():
    print("=== 1. Menghitung Bounding Box Inti + Padding 500m ===")
    padded_bbox = get_padded_bbox()
    print(f"Core BBox   : ({WEST}, {SOUTH}, {EAST}, {NORTH})")
    print(f"Padded BBox : { tuple(round(x, 5) for x in padded_bbox) }")

    # -------------------------------------------------------------------------
    # LAYER 1A: Garis Aliran Sungai Kali Jagir (LineString)
    # -------------------------------------------------------------------------
    river_file = os.path.join(DATA_DIR, "kali_jagir_lines.geojson")
    if not os.path.exists(river_file):
        print("\n=== 2. Mengunduh Layer 1A: Garis Aliran Sungai (waterway=river) ===")
        rivers = fetch_osm_features(padded_bbox, tags={"waterway": "river"})
        rivers = rivers[rivers.geometry.type.isin(["LineString", "MultiLineString"])]
        rivers_clean = clean_columns_for_geojson(rivers, ["id", "osmid", "name", "waterway"])
        rivers_clean.to_file(river_file, driver="GeoJSON")
        print(f"Tersimpan: {river_file} ({len(rivers_clean)} fitur)")
    else:
        print(f"\n[SKIP] Layer 1A ({river_file}) sudah ada.")

    # -------------------------------------------------------------------------
    # LAYER 1B: Poligon Badan Air Sungai (Polygon)
    # -------------------------------------------------------------------------
    water_file = os.path.join(DATA_DIR, "kali_jagir_water_poly.geojson")
    if not os.path.exists(water_file):
        print("\n=== 3. Mengunduh Layer 1B: Poligon Badan Air Sungai ===")
        water_tags = {"natural": "water", "waterway": ["riverbank", "canal"]}
        water_poly = fetch_osm_features(padded_bbox, tags=water_tags)
        water_poly = water_poly[water_poly.geometry.type.isin(["Polygon", "MultiPolygon"])]
        water_clean = clean_columns_for_geojson(water_poly, ["id", "osmid", "name", "natural", "waterway"])
        water_clean.to_file(water_file, driver="GeoJSON")
        print(f"Tersimpan: {water_file} ({len(water_clean)} poligon)")
    else:
        print(f"\n[SKIP] Layer 1B ({water_file}) sudah ada.")

    # -------------------------------------------------------------------------
    # LAYER 2: Tapak Bangunan Warga (Polygon)
    # -------------------------------------------------------------------------
    bldg_file = os.path.join(DATA_DIR, "buildings.geojson")
    if not os.path.exists(bldg_file):
        print("\n=== 4. Mengunduh Layer 2: Tapak Bangunan (building=*) ===")
        buildings = fetch_osm_features(padded_bbox, tags={"building": True})
        buildings = buildings[buildings.geometry.type.isin(["Polygon", "MultiPolygon"])]
        bldg_clean = clean_columns_for_geojson(buildings, ["id", "osmid", "name", "building"])
        bldg_clean.to_file(bldg_file, driver="GeoJSON")
        print(f"Tersimpan: {bldg_file} ({len(bldg_clean)} bangunan)")
    else:
        print(f"\n[SKIP] Layer 2 ({bldg_file}) sudah ada.")

    # -------------------------------------------------------------------------
    # LAYER 3: Fasilitas Umum / Kandidat Shelter (school, college, university, place_of_worship)
    # -------------------------------------------------------------------------
    shelter_file = os.path.join(DATA_DIR, "shelters_raw.geojson")
    if not os.path.exists(shelter_file):
        print("\n=== 5. Mengunduh Layer 3: Titik Evakuasi / Shelter ===")
        # Ambil tepat di Core BBox sesuai penjelasan Bab 2.1 poin 3 (114 objek -> 111 di dalam core)
        shelter_amenities = ["school", "college", "university", "place_of_worship"]
        gdfs = []
        for amenity in shelter_amenities:
            print(f"Mengunduh amenity={amenity}...")
            gdf_part = fetch_osm_features((WEST, SOUTH, EAST, NORTH), tags={"amenity": amenity})
            gdfs.append(gdf_part)

        shelters_raw = pd.concat(gdfs)
        shelters_raw = shelters_raw[~shelters_raw.index.duplicated(keep="first")]

        shelters_clean = clean_columns_for_geojson(
            shelters_raw, ["id", "osmid", "name", "amenity", "religion", "building"]
        )
        shelters_clean.to_file(shelter_file, driver="GeoJSON")
        print(f"Tersimpan: {shelter_file} ({len(shelters_clean)} objek shelter)")
    else:
        print(f"\n[SKIP] Layer 3 ({shelter_file}) sudah ada.")

    # -------------------------------------------------------------------------
    # LAYER 4: Jaringan Jalan Pejalan Kaki (GraphML)
    # -------------------------------------------------------------------------
    walk_file = os.path.join(DATA_DIR, "walk_network.graphml")
    if not os.path.exists(walk_file):
        print("\n=== 6. Mengunduh Layer 4: Jaringan Jalan Pejalan Kaki (network_type='walk') ===")
        G_walk = fetch_osm_graph(padded_bbox, network_type="walk")
        ox.save_graphml(G_walk, filepath=walk_file)
        print(
            f"Tersimpan: {walk_file} "
            f"({G_walk.number_of_nodes()} simpul, {G_walk.number_of_edges()} ruas)"
        )
    else:
        print(f"\n[SKIP] Layer 4 ({walk_file}) sudah ada.")

    print("\nSELESAI! Semua file berhasil disiapkan di folder 'data/' dan siap dipakai offline.")


if __name__ == "__main__":
    main()
