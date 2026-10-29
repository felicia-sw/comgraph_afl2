"""
src/data_layers.py

Modul Pengelolaan Data Spasial, Transformasi CRS, Buffer Bahaya Banjir,
dan Spatial Join untuk Simulasi Luapan Kali Jagir, Wonokromo, Surabaya.

Penanggung Jawab: ORANG 1 (Data Engineer & Lead Integrator)
Mata Kuliah: Grafika Komputer & GIS - Universitas Ciputra
"""

import os
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box, Point, Polygon, MultiPolygon
import osmnx as ox

# =============================================================================
# KONSTANTA SISTEM KOORDINAT & AREA STUDI (Sesuai Proposal Bab 1.2 & 2.1)
# =============================================================================
CRS_DEGREE = "EPSG:4326"    # WGS 84 (Derajat Geografis)
CRS_METER = "EPSG:32749"    # WGS 84 / UTM Zone 49S (Satuan Metrik)

# Bounding Box Area Inti: 112.728 - 112.760 BT, -7.312 s/d -7.292 LS (~7.8 km²)
WEST, SOUTH, EAST, NORTH = 112.728, -7.312, 112.760, -7.292
CORE_BBOX = (WEST, SOUTH, EAST, NORTH)

# Standar Skenario Radius Luapan (m)
DEFAULT_SCENARIOS_M = [15, 50, 100, 200]

# Standar minimum luas tapak jika titik shelter OSM tidak memiliki poligon (m²)
# Luas 150 m² -> kapasitas 50 jiwa (sesuai standar 3 m²/jiwa Perka BNPB No. 7/2008)
DEFAULT_MIN_SHELTER_AREA_M2 = 150.0


def get_study_area_polygon():
    """
    Menghasilkan geometri poligon batas area inti studi dalam sistem proyeksi metrik (EPSG:32749).
    
    Returns:
        shapely.geometry.Polygon: Poligon batas area inti dalam EPSG:32749.
    """
    core_box = box(WEST, SOUTH, EAST, NORTH)
    core_series = gpd.GeoSeries([core_box], crs=CRS_DEGREE)
    return core_series.to_crs(CRS_METER).iloc[0]


def load_all_layers(data_dir="data"):
    """
    Memuat seluruh layer spasial offline dari direktori data/, melakukan transformasi CRS
    ke EPSG:32749 (UTM Zone 49S), memotong ke area inti studi, dan menghitung estimasi kapasitas shelter.
    
    Args:
        data_dir (str): Lokasi folder data lokal.
        
    Returns:
        dict: Kamus berisi GeoDataFrame layer:
            - "rivers": Garis aliran sungai Kali Jagir (LineString)
            - "water": Poligon badan air (Polygon)
            - "jagir_water": Poligon spesifik Kali Jagir (Polygon)
            - "buildings": Tapak bangunan warga dalam area inti (Polygon)
            - "shelters": Titik kandidat shelter dalam area inti lengkap dengan kapasitas (Point)
            - "roads": Jaringan jalan pejalan kaki (LineString)
            - "graph": Graf NetworkX jalan pejalan kaki terproyeksi
            - "study_area": Geometri poligon area studi inti (EPSG:32749)
    """
    study_area = get_study_area_polygon()

    # 1. Layer 1A: Garis Aliran Sungai (LineString)
    rivers_path = os.path.join(data_dir, "kali_jagir_lines.geojson")
    rivers = gpd.read_file(rivers_path).to_crs(CRS_METER).clip(study_area)
    rivers = rivers[rivers.geometry.type.isin(["LineString", "MultiLineString"])].copy()

    # 2. Layer 1B: Poligon Badan Air Sungai (Polygon)
    water_path = os.path.join(data_dir, "kali_jagir_water_poly.geojson")
    water = gpd.read_file(water_path).to_crs(CRS_METER).clip(study_area)
    water = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    
    # Ekstrak poligon spesifik Kali Jagir untuk acuan buffer bahaya luapan
    jagir_water = water[water["name"] == "Kali Jagir"].copy()
    if jagir_water.empty:
        # Fallback jika nama tidak teridentifikasi, gunakan poligon air terbesar
        jagir_water = water.sort_values(by=water.geometry.area, ascending=False).iloc[[0]].copy()

    # 3. Layer 2: Tapak Bangunan Warga (Polygon)
    buildings_path = os.path.join(data_dir, "buildings.geojson")
    buildings = gpd.read_file(buildings_path).to_crs(CRS_METER).clip(study_area)
    buildings = buildings[buildings.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    buildings["luas_tapak_m2"] = buildings.geometry.area

    # 4. Layer 3: Fasilitas Umum / Kandidat Shelter (Point)
    shelters_path = os.path.join(data_dir, "shelters_raw.geojson")
    shelters_raw = gpd.read_file(shelters_path).to_crs(CRS_METER)

    # Simpan luas poligon sebelum konversi ke titik representatif (centroid)
    shelters_raw["poly_area_m2"] = shelters_raw.geometry.area
    shelters = shelters_raw.copy()
    shelters["geometry"] = shelters_raw.geometry.centroid

    # Filter Aturan Proposal: Hanya ambil shelter yang centroid-nya berada di dalam area inti
    # (Dari 114 objek raw, 3 di luar core BBox dieksklusi -> tersisa tepat 111 shelter)
    shelters = shelters[shelters.geometry.within(study_area)].copy()

    # Perhitungan Kapasitas Ruang Evakuasi (Perka BNPB No. 7/2008: 3 m² per jiwa)
    # Jika objek OSM berupa poligon, gunakan luas poligon aslinya.
    # Jika objek OSM berupa Point murni (luas = 0), lakukan spatial join dengan tapak bangunan.
    shelters["luas_tapak_m2"] = shelters["poly_area_m2"]
    point_mask = shelters["luas_tapak_m2"] <= 0
    if point_mask.any():
        points_to_join = shelters[point_mask][["id", "geometry"]]
        joined = gpd.sjoin(points_to_join, buildings[["geometry", "luas_tapak_m2"]], how="left", predicate="intersects")
        # Hilangkan duplikasi jika sebuah titik menyentuh beberapa geometri bangunan
        joined = joined[~joined.index.duplicated(keep="first")]
        shelters.loc[joined.index, "luas_tapak_m2"] = joined["luas_tapak_m2"].fillna(DEFAULT_MIN_SHELTER_AREA_M2)

    # Pastikan tidak ada luas 0 atau negatif, fallback ke nilai default 150 m²
    shelters["luas_tapak_m2"] = shelters["luas_tapak_m2"].replace(0, DEFAULT_MIN_SHELTER_AREA_M2).fillna(DEFAULT_MIN_SHELTER_AREA_M2)
    shelters["kapasitas"] = np.floor(shelters["luas_tapak_m2"] / 3.0).astype(int).clip(lower=1)

    # 5. Layer 4: Jaringan Jalan Pejalan Kaki (Graph & LineString)
    graph_path = os.path.join(data_dir, "walk_network.graphml")
    G_raw = ox.load_graphml(graph_path)
    G_proj = ox.project_graph(G_raw, to_crs=CRS_METER)
    roads = ox.graph_to_gdfs(G_proj, nodes=False).copy()

    return {
        "rivers": rivers,
        "water": water,
        "jagir_water": jagir_water,
        "buildings": buildings,
        "shelters": shelters,
        "roads": roads,
        "graph": G_proj,
        "study_area": study_area,
    }


def validate_layers(layers):
    """
    Memvalidasi seluruh layer spasial (CRS, geometri valid, non-kosong, keunikan ID)
    sesuai checklist evaluasi teknis.
    
    Args:
        layers (dict): Kamus layer yang dihasilkan oleh load_all_layers().
        
    Returns:
        pd.DataFrame: Tabel validasi layer spasial.
    """
    records = []
    layer_names = ["rivers", "water", "jagir_water", "buildings", "shelters", "roads"]
    for name in layer_names:
        gdf = layers[name]
        records.append({
            "Layer": name,
            "Jumlah Fitur": len(gdf),
            "CRS": gdf.crs.to_string(),
            "Geom Valid": int(gdf.is_valid.sum()),
            "Geom Tidak Valid": int((~gdf.is_valid).sum()),
            "Geom Kosong": int(gdf.is_empty.sum()),
            "ID Unik": "Ya" if ("id" in gdf.columns and gdf["id"].is_unique) else ("Ya (Index)" if gdf.index.is_unique else "Tidak"),
        })

    validation_df = pd.DataFrame(records)
    return validation_df


def create_flood_buffer(jagir_water_gdf, radius_m, study_area_poly):
    """
    Operasi GIS 1: Menghasilkan zona bahaya luapan banjir berdasarkan jarak buffer
    dari tepi poligon badan air Kali Jagir (sesuai Permen PUPR No. 28/PRT/M/2015),
    bukan hanya dari garis tengah sungai.
    
    Args:
        jagir_water_gdf (gpd.GeoDataFrame): Poligon badan air Kali Jagir (EPSG:32749).
        radius_m (float): Jarak luapan / buffer dalam meter.
        study_area_poly (shapely.geometry.Polygon): Batas area studi inti untuk pemotongan.
        
    Returns:
        shapely.geometry.Polygon / MultiPolygon: Geometri zona bahaya banjir terpotong area studi.
    """
    if radius_m <= 0:
        return jagir_water_gdf.union_all().intersection(study_area_poly)
    
    buffered = jagir_water_gdf.buffer(radius_m).union_all()
    clipped_zone = buffered.intersection(study_area_poly)
    return clipped_zone


def spatial_join_affected(features_gdf, flood_zone_geom):
    """
    Operasi GIS 2: Melakukan spatial join dengan predikat 'intersects' dalam EPSG:32749
    untuk mendeteksi objek spasial (bangunan atau shelter) yang terdampak genangan air.
    
    Args:
        features_gdf (gpd.GeoDataFrame): GeoDataFrame objek yang dianalisis (bangunan / shelter).
        flood_zone_geom (shapely.geometry.Polygon / MultiPolygon): Geometri zona banjir.
        
    Returns:
        np.ndarray: Array boolean berukuran sama dengan features_gdf (True jika terdampak).
    """
    zone_gdf = gpd.GeoDataFrame(geometry=[flood_zone_geom], crs=CRS_METER)
    joined = gpd.sjoin(features_gdf, zone_gdf, how="left", predicate="intersects")
    is_affected = joined["index_right"].notna().to_numpy()
    return is_affected


def generate_scenario_summary(buildings_gdf, shelters_gdf, jagir_water_gdf, study_area_poly, scenarios=None):
    """
    Menghasilkan tabel ringkasan analisis skenario luapan multi-radius.
    
    Args:
        buildings_gdf (gpd.GeoDataFrame): Layer bangunan warga (EPSG:32749).
        shelters_gdf (gpd.GeoDataFrame): Layer shelter evakuasi (EPSG:32749).
        jagir_water_gdf (gpd.GeoDataFrame): Poligon badan air Kali Jagir.
        study_area_poly (shapely.geometry.Polygon): Batas area studi inti.
        scenarios (list, optional): Daftar radius luapan dalam meter.
        
    Returns:
        pd.DataFrame: Tabel dampak skenario multi-kriteria.
    """
    if scenarios is None:
        scenarios = DEFAULT_SCENARIOS_M

    total_buildings = len(buildings_gdf)
    total_shelters = len(shelters_gdf)
    rows = []

    for r in scenarios:
        zone = create_flood_buffer(jagir_water_gdf, r, study_area_poly)
        hit_buildings = spatial_join_affected(buildings_gdf, zone)
        flooded_shelters = spatial_join_affected(shelters_gdf, zone)

        num_hit_bldgs = int(hit_buildings.sum())
        area_hit_bldgs = float(buildings_gdf.loc[hit_buildings, "luas_tapak_m2"].sum())
        pct_hit_bldgs = (num_hit_bldgs / total_buildings) * 100.0 if total_buildings > 0 else 0.0

        num_flooded_shelters = int(flooded_shelters.sum())
        num_safe_shelters = int((~flooded_shelters).sum())
        safe_capacity = int(shelters_gdf.loc[~flooded_shelters, "kapasitas"].sum())

        rows.append({
            "Radius Luapan (m)": r,
            "Bangunan Terdampak (Unit)": num_hit_bldgs,
            "Persentase Bangunan (%)": round(pct_hit_bldgs, 2),
            "Luas Tapak Terdampak (m²)": round(area_hit_bldgs, 1),
            "Shelter Tergenang (Titik)": num_flooded_shelters,
            "Shelter Aman (Titik)": num_safe_shelters,
            "Total Kapasitas Shelter Aman (Jiwa)": safe_capacity,
        })

    summary_df = pd.DataFrame(rows)
    return summary_df
