"""
src/graphics.py

Orang 3: Peta, Interaksi & Animasi.
Mata Kuliah: Grafika Komputer & GIS - Universitas Ciputra

Isi modul:
  1. translate()           -> geser titik dengan matriks translasi homogen 3x3 (Week 3)
  2. walk_position()       -> posisi warga di rute, Bezier linear p(t) = (1-t)P0 + tP1
  3. attach_start()        -> sambungkan posisi warga ke awal garis rute
  4. draw_map()            -> gambar SATU peta lengkap
  5. make_scenario_maps()  -> peta beberapa skenario berdampingan
  6. build_dashboard()     -> slider, tombol U/S/T/B, input koordinat, kartu info
  7. make_animation()      -> FuncAnimation (zona meluas + warga berjalan) -> GIF

Semua koordinat memakai EPSG:32749 (meter), sama dengan hasil dl.load_all_layers().
Fungsi milik Orang 1 / Orang 2 DIKIRIM LEWAT PARAMETER (zone_fn, status_fn, route_fn),
jadi file ini tidak meng-import data_layers.py maupun analysis.py.
"""

import os

import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from pyproj import Transformer
from shapely.geometry import Point, LineString

CRS_DEGREE = "EPSG:4326"
CRS_METER = "EPSG:32749"

# Posisi awal warga (Simpang Jalan Jagir), format (lon, lat), sama dengan notebook tim
RESIDENT_START_DEG = (112.75026, -7.30208)

# =============================================================================
# WARNA & URUTAN GAMBAR (zorder: kecil = digambar duluan = di bawah)
# Urutan proposal: zona -> sungai -> bangunan -> jalan & rute -> shelter -> warga -> label
# =============================================================================
COLORS = {
    "background": "#f4f1ea",
    "zone": "#e63946",
    "river": "#3a86ff",
    "building_safe": "#b8b8b8",
    "building_hit": "#d62828",
    "road": "#8d8d8d",
    "route": "#ffd60a",
    "route_edge": "#3d3d3d",
    "shelter_safe": "#2a9d4a",
    "shelter_hit": "#d62828",
    "resident": "#111111",
}
Z = {"zone": 1, "river": 2, "building": 3, "road": 4, "route": 5,
     "shelter": 6, "resident": 7, "label": 8, "boundary": 9}


# =============================================================================
# FUNGSI BANTU
# =============================================================================
def _clean_name(value, fallback):
    """Nama shelter dari OSM kadang kosong/NaN/'None'. Kembalikan teks yang rapi."""
    if isinstance(value, str) and value.strip() and value.strip().lower() not in ("nan", "none"):
        return value.strip()
    return fallback


def resident_from_lonlat(lon, lat):
    """Ubah koordinat derajat (lon, lat) menjadi Point dalam meter (EPSG:32749)."""
    x, y = Transformer.from_crs(CRS_DEGREE, CRS_METER, always_xy=True).transform(lon, lat)
    return Point(x, y)


def _ensure_dir(path):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


# =============================================================================
# 1. TRANSLASI (matriks homogen, bentuk baris)
# =============================================================================
def translate(point, tx, ty):
    """
    Geser titik sejauh (tx, ty) meter dengan matriks translasi homogen 3x3.

        [x' y' 1] = [x y 1] x | 1  0  0 |
                              | 0  1  0 |
                              | tx ty 1 |

    Translasi tidak bisa ditulis sebagai perkalian matriks 2x2. Dengan menambah
    koordinat ketiga bernilai 1 (koordinat homogen), geser menjadi perkalian
    matriks, sehingga bisa digabung dengan rotasi dan skala.
    """
    T = np.array([
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [tx, ty, 1.0],
    ])
    x_new, y_new, _ = np.array([point.x, point.y, 1.0]) @ T
    return Point(x_new, y_new)


# =============================================================================
# 2. POSISI WARGA DI SEPANJANG RUTE (Bezier linear)
# =============================================================================
def walk_position(line, t):
    """
    Posisi warga di garis rute untuk t = 0 (awal) sampai t = 1 (akhir).

    Rute adalah polyline (banyak segmen lurus). Pada satu segmen P0 -> P1 dipakai
    interpolasi linear (= kurva Bezier linear):
            p(u) = (1 - u) * P0 + u * P1 ,   0 <= u <= 1
    t dari seluruh rute diubah dulu menjadi jarak tempuh, lalu dicari segmen
    tempat warga berada dan u = posisi di dalam segmen itu. Kecepatan konstan.
    """
    coords = np.asarray(line.coords, dtype=float)[:, :2]
    if len(coords) == 1:
        return Point(coords[0])

    t = min(max(float(t), 0.0), 1.0)
    seg = np.diff(coords, axis=0)
    seg_len = np.hypot(seg[:, 0], seg[:, 1])
    total = seg_len.sum()
    if total == 0:
        return Point(coords[0])

    target = t * total
    cum = np.cumsum(seg_len)
    i = min(int(np.searchsorted(cum, target, side="left")), len(seg_len) - 1)
    u = (target - (cum[i] - seg_len[i])) / seg_len[i] if seg_len[i] > 0 else 0.0
    u = min(max(u, 0.0), 1.0)

    p = (1 - u) * coords[i] + u * coords[i + 1]
    return Point(p[0], p[1])


def attach_start(resident, routes):
    """
    Rute dari analysis.py dimulai di simpul jalan terdekat, bukan di posisi warga.
    Fungsi ini menambahkan posisi warga di awal garis supaya rute tersambung ke warga.
    """
    if resident is None or not routes:
        return routes or []
    out = []
    for r in routes:
        coords = [(resident.x, resident.y)] + [tuple(c[:2]) for c in r["rute"].coords]
        new_r = dict(r)
        new_r["rute"] = LineString(coords)
        out.append(new_r)
    return out


# =============================================================================
# 3. MENGGAMBAR SATU PETA
# =============================================================================
def draw_map(ax, layers, zone, resident=None, routes=None, title=None, legend=True):
    """
    Gambar peta lengkap pada sumbu `ax`.

    Args:
        ax:       sumbu matplotlib (dari plt.subplots()).
        layers:   dict dari dl.load_all_layers().
        zone:     poligon zona bahaya (dl.create_flood_buffer).
        resident: Point posisi warga (EPSG:32749), boleh None.
        routes:   list dict dari top_evacuation_routes, boleh None / kosong.
        title:    judul peta.
        legend:   True = tampilkan legenda.
    """
    study_area = layers["study_area"]
    ax.set_facecolor(COLORS["background"])
    zone_ok = zone is not None and not zone.is_empty

    # 1) Zona bahaya: merah transparan
    if zone_ok:
        gpd.GeoSeries([zone]).plot(ax=ax, color=COLORS["zone"], alpha=0.30, zorder=Z["zone"])

    # 2) Sungai: biru
    if len(layers["water"]):
        layers["water"].plot(ax=ax, color=COLORS["river"], zorder=Z["river"])
    if len(layers["rivers"]):
        layers["rivers"].plot(ax=ax, color=COLORS["river"], linewidth=1.2, zorder=Z["river"])

    # 3) Bangunan: abu-abu, merah jika terdampak
    bld = layers["buildings"]
    hit_b = bld.intersects(zone).to_numpy() if zone_ok else np.zeros(len(bld), dtype=bool)
    if (~hit_b).any():
        bld[~hit_b].plot(ax=ax, color=COLORS["building_safe"], linewidth=0, zorder=Z["building"])
    if hit_b.any():
        bld[hit_b].plot(ax=ax, color=COLORS["building_hit"], linewidth=0, zorder=Z["building"])

    # 4) Jalan (abu tipis) lalu rute evakuasi (kuning dengan garis tepi gelap)
    if len(layers["roads"]):
        layers["roads"].plot(ax=ax, color=COLORS["road"], linewidth=0.5, zorder=Z["road"])
    for r in (routes or []):
        xs, ys = r["rute"].xy
        ax.plot(xs, ys, color=COLORS["route_edge"], linewidth=5,
                solid_capstyle="round", zorder=Z["route"])
        ax.plot(xs, ys, color=COLORS["route"], linewidth=3,
                solid_capstyle="round", zorder=Z["route"] + 0.1)

    # 5) Shelter: hijau = aman, merah = tergenang
    sh = layers["shelters"]
    hit_s = sh.intersects(zone).to_numpy() if zone_ok else np.zeros(len(sh), dtype=bool)
    for mask, key in ((~hit_s, "shelter_safe"), (hit_s, "shelter_hit")):
        if mask.any():
            s = sh[mask]
            ax.scatter(s.geometry.x, s.geometry.y, s=40, marker="s", c=COLORS[key],
                       edgecolors="white", linewidths=0.8, zorder=Z["shelter"])

    # 6) Warga
    if resident is not None:
        ax.scatter([resident.x], [resident.y], s=130, marker="o", c=COLORS["resident"],
                   edgecolors="white", linewidths=1.5, zorder=Z["resident"])
        ax.annotate("Warga", (resident.x, resident.y), xytext=(8, 8),
                    textcoords="offset points", fontsize=9, fontweight="bold",
                    zorder=Z["label"])

    # 7) Label
    if len(layers["jagir_water"]):
        p = layers["jagir_water"].geometry.union_all().representative_point()
        ax.annotate("Kali Jagir", (p.x, p.y), fontsize=9, style="italic", color="#1d4ed8",
                    zorder=Z["label"],
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7, lw=0))
    for r in (routes or []):
        ex, ey = r["rute"].coords[-1][:2]
        nama = _clean_name(r.get("nama"), str(r.get("jenis", "Shelter")))
        ax.annotate(f"{nama}\n{r['jarak_m']} m", (ex, ey), xytext=(6, -14),
                    textcoords="offset points", fontsize=7, zorder=Z["label"],
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8, lw=0))

    # Batas area inti studi
    gpd.GeoSeries([study_area]).boundary.plot(ax=ax, color="black", linestyle="--",
                                              linewidth=1.2, zorder=Z["boundary"])

    minx, miny, maxx, maxy = study_area.bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.set_xlabel("Easting (m, UTM 49S)", fontsize=8)
    ax.set_ylabel("Northing (m, UTM 49S)", fontsize=8)
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold")

    # 8) Legenda
    if legend:
        handles = [
            Patch(facecolor=COLORS["river"], label="Sungai"),
            Patch(facecolor=COLORS["zone"], alpha=0.30, label="Zona bahaya"),
            Patch(facecolor=COLORS["building_safe"], label="Bangunan aman"),
            Patch(facecolor=COLORS["building_hit"], label="Bangunan terdampak"),
            Line2D([0], [0], marker="s", color="w", markerfacecolor=COLORS["shelter_safe"],
                   markersize=8, label="Shelter aman"),
            Line2D([0], [0], marker="s", color="w", markerfacecolor=COLORS["shelter_hit"],
                   markersize=8, label="Shelter tergenang"),
            Line2D([0], [0], color=COLORS["route"], linewidth=3, label="Rute evakuasi"),
            Line2D([0], [0], marker="o", color="w", markerfacecolor=COLORS["resident"],
                   markersize=9, label="Warga"),
            Line2D([0], [0], color="black", linestyle="--", linewidth=1, label="Batas area inti"),
        ]
        ax.legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.9)


# =============================================================================
# 4. PETA BEBERAPA SKENARIO BERDAMPINGAN
# =============================================================================
def make_scenario_maps(layers, zone_fn, radii=(15, 100, 200), resident=None,
                       route_fn=None, status_fn=None, save_path=None):
    """
    Args:
        zone_fn:   r -> poligon zona
        route_fn:  (point, zone) -> list rute (boleh None)
        status_fn: (point, zone) -> "AMAN"/"BAHAYA" (boleh None)
        save_path: contoh "output/skenario.png"
    """
    n = len(radii)
    fig, axes = plt.subplots(1, n, figsize=(7 * n, 7))
    axes = np.atleast_1d(axes)

    for i, (ax, r) in enumerate(zip(axes, radii)):
        zone = zone_fn(r)
        routes, suffix = [], ""
        if resident is not None and status_fn is not None:
            status = status_fn(resident, zone)
            suffix = f" - warga {status}"
            if status == "BAHAYA" and route_fn is not None:
                routes = attach_start(resident, route_fn(resident, zone))
        draw_map(ax, layers, zone, resident, routes,
                 title=f"Luapan {r} m{suffix}", legend=(i == 0))

    fig.tight_layout()
    if save_path:
        _ensure_dir(save_path)
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


# =============================================================================
# 5. DASHBOARD INTERAKTIF (ipywidgets)
# =============================================================================
def _info_card_html(status, n_hit, n_total, routes, radius):
    color = "#d62828" if status == "BAHAYA" else "#2a9d4a"
    html = (f"<div style='border:2px solid {color};border-radius:8px;padding:10px;"
            f"max-width:560px;font-family:sans-serif'>"
            f"<b>Status warga:</b> <span style='color:{color};font-weight:bold'>{status}</span><br>"
            f"<b>Radius luapan:</b> {radius} m<br>"
            f"<b>Bangunan terdampak:</b> {n_hit:,} dari {n_total:,}<br>")
    if status == "AMAN":
        html += "<i>Warga berada di luar zona bahaya, tidak perlu evakuasi.</i>"
    elif not routes:
        html += ("<b style='color:#d62828'>Tidak ada rute kering ke shelter mana pun "
                 "(jalan terputus oleh genangan).</b>")
    else:
        html += "<b>Shelter aman terdekat:</b><ol style='margin:4px 0'>"
        for r in routes:
            nama = _clean_name(r.get("nama"), "(tanpa nama)")
            html += (f"<li>{nama} ({r.get('jenis', '-')}) - {r['jarak_m']} m, "
                     f"kapasitas {r['kapasitas']} jiwa</li>")
        html += "</ol>"
    return html + "</div>"


def build_dashboard(layers, zone_fn, status_fn, route_fn, start_point, default_step=50):
    """
    Dashboard: slider radius, kotak langkah (m), tombol Utara/Selatan/Timur/Barat,
    input koordinat (lon/lat), peta, dan kartu info.
    """
    import ipywidgets as widgets
    from IPython.display import display, clear_output, HTML

    to_utm = Transformer.from_crs(CRS_DEGREE, CRS_METER, always_xy=True)
    to_wgs = Transformer.from_crs(CRS_METER, CRS_DEGREE, always_xy=True)

    state = {"resident": start_point}
    zone_cache = {}

    def get_zone(r):
        if r not in zone_cache:
            zone_cache[r] = zone_fn(r)
        return zone_cache[r]

    slider = widgets.IntSlider(value=15, min=15, max=200, step=5, description="Radius (m):",
                               continuous_update=False, style={"description_width": "initial"},
                               layout=widgets.Layout(width="460px"))
    step_box = widgets.BoundedFloatText(value=default_step, min=1, max=1000, step=10,
                                        description="Langkah (m):",
                                        style={"description_width": "initial"})
    btn_n = widgets.Button(description="Utara", icon="arrow-up")
    btn_s = widgets.Button(description="Selatan", icon="arrow-down")
    btn_e = widgets.Button(description="Timur", icon="arrow-right")
    btn_w = widgets.Button(description="Barat", icon="arrow-left")

    lon0, lat0 = to_wgs.transform(start_point.x, start_point.y)
    lon_box = widgets.FloatText(value=round(lon0, 6), description="Lon (BT):")
    lat_box = widgets.FloatText(value=round(lat0, 6), description="Lat (LS):")
    btn_goto = widgets.Button(description="Pindah ke koordinat", button_style="info")

    msg = widgets.HTML("")
    out = widgets.Output()

    def sync_coord_boxes():
        lon, lat = to_wgs.transform(state["resident"].x, state["resident"].y)
        lon_box.value, lat_box.value = round(lon, 6), round(lat, 6)

    def refresh():
        zone = get_zone(slider.value)
        p = state["resident"]
        status = status_fn(p, zone)
        routes = route_fn(p, zone) if status == "BAHAYA" else []
        bld = layers["buildings"]
        n_hit = 0 if zone.is_empty else int(bld.intersects(zone).sum())

        with out:
            clear_output(wait=True)
            fig, ax = plt.subplots(figsize=(9, 9))
            draw_map(ax, layers, zone, p, attach_start(p, routes),
                     title=f"Skenario luapan {slider.value} m - warga {status}")
            plt.show()
            plt.close(fig)
            display(HTML(_info_card_html(status, n_hit, len(bld), routes, slider.value)))

    def move(dx, dy):
        new_p = translate(state["resident"], dx, dy)
        if not new_p.within(layers["study_area"]):
            msg.value = "<span style='color:#d62828'>Gerakan dibatalkan: keluar dari area studi.</span>"
            return
        msg.value = ""
        state["resident"] = new_p
        sync_coord_boxes()
        refresh()

    def goto(_):
        x, y = to_utm.transform(lon_box.value, lat_box.value)
        new_p = Point(x, y)
        if not new_p.within(layers["study_area"]):
            msg.value = ("<span style='color:#d62828'>Koordinat di luar area studi "
                         "(112.728-112.760 BT, -7.312 s/d -7.292 LS).</span>")
            return
        msg.value = ""
        state["resident"] = new_p
        refresh()

    btn_n.on_click(lambda _: move(0, step_box.value))
    btn_s.on_click(lambda _: move(0, -step_box.value))
    btn_e.on_click(lambda _: move(step_box.value, 0))
    btn_w.on_click(lambda _: move(-step_box.value, 0))
    btn_goto.on_click(goto)
    slider.observe(lambda change: refresh(), names="value")

    display(widgets.VBox([
        slider,
        step_box,
        widgets.HBox([btn_w, btn_n, btn_s, btn_e]),
        widgets.HBox([lon_box, lat_box, btn_goto]),
        msg,
        out,
    ]))
    refresh()


# =============================================================================
# 6. ANIMASI (FuncAnimation) -> GIF
# =============================================================================
def make_animation(layers, zone_fn, route_fn, resident, r_start=15, r_end=200,
                   n_zone_frames=15, n_walk_frames=20, n_hold_frames=4,
                   save_path="output/evakuasi.gif", fps=5):
    """
    Dua tahap:
      1) radius naik r_start -> r_end (zona bahaya meluas)
      2) warga berjalan menyusuri rute terbaik pada zona akhir (r_end)

    GIF: tiap frame digambar menjadi satu gambar, lalu PillowWriter menyusun semuanya.
    Dengan 36 ribu bangunan tiap frame butuh beberapa detik, jadi total bisa beberapa menit.
    """
    # Siapkan semua frame (hanya data) lebih dulu
    frames = []
    for r in np.linspace(r_start, r_end, n_zone_frames):
        frames.append({"zone": zone_fn(r), "resident": resident, "routes": [],
                       "title": f"Luapan naik: {r:.0f} m"})

    final_zone = zone_fn(r_end)
    routes = attach_start(resident, route_fn(resident, final_zone))
    if routes:
        best = routes[0]
        for t in np.linspace(0, 1, n_walk_frames):
            frames.append({"zone": final_zone, "resident": walk_position(best["rute"], t),
                           "routes": [best],
                           "title": f"Warga berjalan ke shelter (luapan {r_end} m)"})
        for _ in range(n_hold_frames):
            frames.append({"zone": final_zone, "resident": walk_position(best["rute"], 1.0),
                           "routes": [best], "title": "Warga tiba di shelter"})
    else:
        for _ in range(n_hold_frames):
            frames.append({"zone": final_zone, "resident": resident, "routes": [],
                           "title": f"Tidak ada rute kering (luapan {r_end} m)"})

    fig, ax = plt.subplots(figsize=(8, 8))

    def update(i):
        ax.clear()
        f = frames[i]
        draw_map(ax, layers, f["zone"], f["resident"], f["routes"], title=f["title"])
        return []

    anim = FuncAnimation(fig, update, frames=len(frames), interval=1000 / fps,
                         blit=False, repeat=False)
    _ensure_dir(save_path)
    anim.save(save_path, writer=PillowWriter(fps=fps), dpi=80)
    plt.close(fig)
    return save_path
