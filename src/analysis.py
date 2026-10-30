"""
src/analysis.py

Orang 2: gerak warga (matriks translasi homogen), status warga (point-in-polygon),
dan rute evakuasi di jalan kering (shortest path).
"""

import numpy as np
import networkx as nx
import osmnx as ox
from shapely.geometry import Point, LineString

TOP_N_SHELTERS = 3

def move_citizen(point, tx, ty):
    """Geser titik warga sejauh (tx, ty) meter dengan matriks translasi homogen (bentuk baris, Week 3).

    [x' y' 1] = [x y 1] x [[1, 0, 0], [0, 1, 0], [tx, ty, 1]]
    """
    T = np.array([
        [1, 0, 0],
        [0, 1, 0],
        [tx, ty, 1],
    ])
    x_new, y_new, _ = np.array([point.x, point.y, 1]) @ T
    return Point(x_new, y_new)

def citizen_status(point, zone):
    """Operasi GIS 3: point-in-polygon. BAHAYA jika titik warga ada di dalam zona banjir."""
    return "BAHAYA" if point.within(zone) else "AMAN"

def dry_graph(graph, roads, zone):
    """Salin graf jalan lalu hapus ruas yang menyentuh zona banjir dan simpul yang jadi terisolasi."""
    flooded = roads[roads.intersects(zone)].index  # index = (u, v, key)
    g = graph.copy()
    g.remove_edges_from(flooded)
    g.remove_nodes_from(list(nx.isolates(g)))
    return g

def top_evacuation_routes(point, zone, graph, roads, shelters, safe_mask, n=TOP_N_SHELTERS):
    """Operasi GIS 4: n shelter aman terdekat lewat jalan kering (Dijkstra, bobot = panjang ruas).

    Returns:
        list[dict]: tiap item berisi nama, jenis, kapasitas, jarak_m, dan garis rute (LineString).
                    List kosong berarti warga tidak punya jalan kering ke shelter mana pun.
    """
    g = dry_graph(graph, roads, zone)
    if g.number_of_nodes() == 0:
        return []

    safe = shelters[safe_mask]
    start = ox.distance.nearest_nodes(g, point.x, point.y)
    targets = ox.distance.nearest_nodes(g, safe.geometry.x, safe.geometry.y)

    distances, paths = nx.single_source_dijkstra(g, start, weight="length")
    candidates = []
    for (_, shelter), node in zip(safe.iterrows(), targets):
        if node in distances:
            candidates.append((distances[node], node, shelter))
    candidates.sort(key=lambda c: c[0])

    routes = []
    for dist, node, shelter in candidates[:n]:
        coords = [(g.nodes[v]["x"], g.nodes[v]["y"]) for v in paths[node]]
        if len(coords) == 1:
            coords = coords * 2
        routes.append(
            {
                "nama": shelter.get("name"),
                "jenis": shelter["amenity"],
                "kapasitas": int(shelter["kapasitas"]),
                "jarak_m": round(dist),
                "rute": LineString(coords),
            })
    return routes