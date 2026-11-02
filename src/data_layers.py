import os
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import box, Point, Polygon, MultiPolygon
import osmnx as ox

CRS_DEGREE = "EPSG:4326"
CRS_METER = "EPSG:32749"

WEST, SOUTH, EAST, NORTH = 112.728, -7.312, 112.760, -7.292
CORE_BBOX = (WEST, SOUTH, EAST, NORTH)

DEFAULT_SCENARIOS_M = [15, 100, 200]

DEFAULT_MIN_SHELTER_AREA_M2 = 150.0


def get_study_area_polygon():
    core_box = box(WEST, SOUTH, EAST, NORTH)
    core_series = gpd.GeoSeries([core_box], crs=CRS_DEGREE)
    return core_series.to_crs(CRS_METER).iloc[0]


def load_all_layers(data_dir="data"):
    study_area = get_study_area_polygon()

    # Garis aliran sungai (ls)
    rivers_path = os.path.join(data_dir, "kali_jagir_lines.geojson")
    rivers = gpd.read_file(rivers_path).to_crs(CRS_METER).clip(study_area)
    rivers = rivers[rivers.geometry.type.isin(["LineString", "MultiLineString"])].copy()

    # Poligon badan air sungai (poly)
    water_path = os.path.join(data_dir, "kali_jagir_water_poly.geojson")
    water = gpd.read_file(water_path).to_crs(CRS_METER)
    water = water[water.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    
    # extract poligon spesifik Jagir untuk acuan buffer bahaya luapan
    jagir_water = water[water["name"] == "Kali Jagir"].copy()
    if jagir_water.empty:
        # Fallback if name is unknown, pake poligon air terbesar
        jagir_water = water.sort_values(by=water.geometry.area, ascending=False).iloc[[0]].copy()

    # tapak Bangunan warga (poly)
    buildings_path = os.path.join(data_dir, "buildings.geojson")
    buildings_all = gpd.read_file(buildings_path).to_crs(CRS_METER)
    buildings = buildings_all.clip(study_area)
    buildings = buildings[buildings.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    buildings["luas_tapak_m2"] = buildings.geometry.area

    # Fasilitas umum / kandidat shelter (Point)
    shelters_path = os.path.join(data_dir, "shelters_raw.geojson")
    shelters_raw = gpd.read_file(shelters_path).to_crs(CRS_METER)

    # Dari 114 objek raw hasil query bbox area inti, 3 objek dengan centroid di luar core BBox
    # hasil: 55 tempat ibadah, 47 sekolah, 9 kampusi
    shelters = shelters_raw[shelters_raw.geometry.centroid.within(study_area)].copy()

    # Perhitungan Kapasitas Ruang Evakuasi (Perka BNPB No. 7/2008: 3 m² per jiwa):
    # Poligon sekolah/kampus di OSM merupakan luas batas lahan (termasuk halaman, lapangan, parkir).
    # Kapasitas dihitung dari luas tapak bangunan aktual di dalam poligon shelter:
    shelter_polys = shelters[shelters.geometry.type.isin(["Polygon", "MultiPolygon"])].copy()
    if not shelter_polys.empty:
        inside_buildings = gpd.overlay(
            buildings_all[["geometry"]],
            shelter_polys[["id", "geometry"]],
            how="intersection",
            keep_geom_type=False
        )
        inside_buildings["area"] = inside_buildings.geometry.area
        footprint_by_shelter = inside_buildings.groupby("id")["area"].sum()
        shelters["luas_tapak_m2"] = shelters["id"].map(footprint_by_shelter).fillna(0.0)
    else:
        shelters["luas_tapak_m2"] = 0.0

    point_mask = shelters["luas_tapak_m2"] <= 0
    if point_mask.any():
        points_to_join = shelters[point_mask][["id", "geometry"]]
        joined = gpd.sjoin(points_to_join, buildings_all[["geometry"]], how="left", predicate="intersects")
        joined["bldg_area"] = joined.index_right.map(buildings_all.geometry.area)
        joined = joined[~joined.index.duplicated(keep="first")]
        for _, row in joined.iterrows():
            if pd.notna(row["bldg_area"]) and row["bldg_area"] > 0:
                shelters.loc[shelters["id"] == row["id"], "luas_tapak_m2"] = row["bldg_area"]
            else:
                shelters.loc[shelters["id"] == row["id"], "luas_tapak_m2"] = DEFAULT_MIN_SHELTER_AREA_M2

    shelters["kapasitas"] = np.floor(shelters["luas_tapak_m2"] / 3.0).astype(int).clip(lower=1)
    
    # representasikan geometri seluruh shelter sebagai point untuk analisis jarak & perutean
    shelters["geometry"] = shelters.geometry.centroid

    # walkable street (Graph & LineString)
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



#GIS Operation 1: buat zona yg bahaya hasil bufferdaraai tepi sungai (soalnya ngikut yg permen)
def create_flood_buffer(jagir_water_gdf, radius_m, study_area_poly=None):
    if study_area_poly is None:
        study_area_poly = get_study_area_polygon()
    if radius_m <= 0:
        return jagir_water_gdf.union_all().intersection(study_area_poly)
    
    buffered = jagir_water_gdf.buffer(radius_m).union_all()
    clipped_zone = buffered.intersection(study_area_poly)
    return clipped_zone

#GIS Operation 2: spatial join antara fitur sama zona bahaya (harus intresect g bis within)
def spatial_join_affected(features_gdf, flood_zone_geom):
    zone_gdf = gpd.GeoDataFrame(geometry=[flood_zone_geom], crs=CRS_METER)
    joined = gpd.sjoin(features_gdf, zone_gdf, how="left", predicate="intersects")
    is_affected = joined["index_right"].notna().to_numpy()
    return is_affected

#GIS Operation 3: ringkasan skenario luapan multi radius (in tbale format)
def generate_scenario_summary(buildings_gdf, shelters_gdf, jagir_water_gdf, study_area_poly=None, scenarios=None):
    if study_area_poly is None:
        study_area_poly = get_study_area_polygon()
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
