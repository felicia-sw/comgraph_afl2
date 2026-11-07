import os

import numpy as np
import matplotlib.pyplot as plt
import geopandas as gpd
from matplotlib.animation import FuncAnimation, PillowWriter
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from pyproj import Transformer
from shapely.geometry import Point, LineString

from src.analysis import move_citizen

CRS_DEGREE = "EPSG:4326"
CRS_METER = "EPSG:32749"

RESIDENT_START_DEG = (112.75026, -7.30208)

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


def _clean_name(value, fallback):
    if isinstance(value, str) and value.strip() and value.strip().lower() not in ("nan", "none"):
        return value.strip()
    return fallback


def resident_from_lonlat(lon, lat):
    x, y = Transformer.from_crs(CRS_DEGREE, CRS_METER, always_xy=True).transform(lon, lat)
    return Point(x, y)


def _ensure_dir(path):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)


def walk_position(line, t):
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
    if resident is None or not routes:
        return routes or []
    out = []
    for r in routes:
        coords = [(resident.x, resident.y)] + [tuple(c[:2]) for c in r["rute"].coords]
        new_r = dict(r)
        new_r["rute"] = LineString(coords)
        out.append(new_r)
    return out


def draw_map(ax, layers, zone, resident=None, routes=None, title=None, legend=True, hit_b=None, hit_s=None):
    study_area = layers["study_area"]
    ax.set_facecolor(COLORS["background"])
    zone_ok = zone is not None and not zone.is_empty

    if zone_ok:
        gpd.GeoSeries([zone]).plot(ax=ax, color=COLORS["zone"], alpha=0.30, zorder=Z["zone"])

    if len(layers["water"]):
        layers["water"].plot(ax=ax, color=COLORS["river"], zorder=Z["river"])
    if len(layers["rivers"]):
        layers["rivers"].plot(ax=ax, color=COLORS["river"], linewidth=1.2, zorder=Z["river"])

    bld = layers["buildings"]
    if hit_b is None:
        hit_b = bld.intersects(zone).to_numpy() if zone_ok else np.zeros(len(bld), dtype=bool)
        
    if (~hit_b).any():
        bld[~hit_b].plot(ax=ax, color=COLORS["building_safe"], linewidth=0, zorder=Z["building"], rasterized=True)
    if hit_b.any():
        bld[hit_b].plot(ax=ax, color=COLORS["building_hit"], linewidth=0, zorder=Z["building"], rasterized=True)

    if len(layers["roads"]):
        layers["roads"].plot(ax=ax, color=COLORS["road"], linewidth=0.5, zorder=Z["road"], rasterized=True)
    
    for r in (routes or []):
        xs, ys = r["rute"].xy
        ax.plot(xs, ys, color=COLORS["route_edge"], linewidth=5,
                solid_capstyle="round", zorder=Z["route"])
        ax.plot(xs, ys, color=COLORS["route"], linewidth=3,
                solid_capstyle="round", zorder=Z["route"] + 0.1)

    sh = layers["shelters"]
    if hit_s is None:
        hit_s = sh.intersects(zone).to_numpy() if zone_ok else np.zeros(len(sh), dtype=bool)
        
    for mask, key in ((~hit_s, "shelter_safe"), (hit_s, "shelter_hit")):
        if mask.any():
            s = sh[mask]
            ax.scatter(s.geometry.x, s.geometry.y, s=40, marker="s", c=COLORS[key],
                       edgecolors="white", linewidths=0.8, zorder=Z["shelter"])

    if resident is not None:
        ax.scatter([resident.x], [resident.y], s=130, marker="o", c=COLORS["resident"],
                   edgecolors="white", linewidths=1.5, zorder=Z["resident"])
        ax.annotate("Warga", (resident.x, resident.y), xytext=(8, 8),
                    textcoords="offset points", fontsize=9, fontweight="bold",
                    zorder=Z["label"])

    if len(layers["jagir_water"]):
        p = layers["jagir_water"].geometry.union_all().intersection(study_area).representative_point()
        ax.annotate("Kali Jagir", (p.x, p.y), fontsize=9, style="italic", color="#1d4ed8",
                    zorder=Z["label"],
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.7, lw=0))
    for i, r in enumerate(routes or []):
        ex, ey = r["rute"].coords[-1][:2]
        nama = _clean_name(r.get("nama"), str(r.get("jenis", "Shelter")))
        ax.annotate(f"{i + 1}. {nama}\n{r['jarak_m']} m", (ex, ey), xytext=(8, 6 - 26 * i),
                    textcoords="offset points", fontsize=7, zorder=Z["label"],
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", alpha=0.8, lw=0))

    gpd.GeoSeries([study_area]).boundary.plot(ax=ax, color="black", linestyle="--",
                                              linewidth=1.2, zorder=Z["boundary"])

    minx, miny, maxx, maxy = study_area.bounds
    ax.set_xlim(minx, maxx)
    ax.set_ylim(miny, maxy)
    ax.set_aspect("equal")
    ax.tick_params(labelsize=7)
    ax.ticklabel_format(useOffset=False, style="plain")
    ax.set_xlabel("Easting (m, UTM 49S)", fontsize=8)
    ax.set_ylabel("Northing (m, UTM 49S)", fontsize=8)
    if title:
        ax.set_title(title, fontsize=11, fontweight="bold")

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
        ax.legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.9).set_zorder(20)
        
def make_scenario_maps(layers, zone_fn, radii=(15, 100, 200), resident=None,
                       route_fn=None, status_fn=None, save_path=None):
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
    import ipywidgets as widgets
    from IPython.display import display, HTML
    from geopy.geocoders import Nominatim
    import numpy as np
    import io
    import matplotlib.pyplot as plt
    from shapely.geometry import Point, LineString 

    to_utm = Transformer.from_crs(CRS_DEGREE, CRS_METER, always_xy=True)
    to_wgs = Transformer.from_crs(CRS_METER, CRS_DEGREE, always_xy=True)

    state = {"resident": start_point}
    
    if "buildings" in layers:
        layers["buildings"] = layers["buildings"].simplify(10)
    if "roads" in layers:
        layers["roads"] = layers["roads"].simplify(10)
    if "rivers" in layers:
        layers["rivers"] = layers["rivers"].simplify(10)
        
    zone_cache = {}
    route_cache = {}
    hit_cache = {}  

    def get_zone(r):
        if r not in zone_cache:
            zone_cache[r] = zone_fn(r)
        return zone_cache[r]
        
    def get_route(p, zone):
        cache_id = (round(zone.area), round(p.x), round(p.y))
        if cache_id not in route_cache:
            route_cache[cache_id] = route_fn(p, zone)
        return route_cache[cache_id]
        
    def get_hit_data(r, zone):
        if r not in hit_cache:
            bld = layers["buildings"]
            sh = layers["shelters"]
            if zone.is_empty:
                hit_b = np.zeros(len(bld), dtype=bool)
                hit_s = np.zeros(len(sh), dtype=bool)
                n_hit = 0
            else:
                hit_b = bld.intersects(zone).to_numpy()
                hit_s = sh.intersects(zone).to_numpy()
                n_hit = int(hit_b.sum())
            hit_cache[r] = (hit_b, hit_s, n_hit)
        return hit_cache[r]

    def fix_route_endpoints(resident, routes, shelters, hit_s):
        if resident is None or not routes:
            return routes or []
        out = []
        safe_shelters = shelters[~hit_s] if hit_s is not None else shelters
        for r in routes:
            rc = [tuple(c[:2]) for c in r["rute"].coords]
            coords = [(resident.x, resident.y)] + rc
            
            if not safe_shelters.empty:
                end_pt = Point(rc[-1])
                closest_idx = safe_shelters.distance(end_pt).idxmin()
                sg = safe_shelters.loc[closest_idx].geometry
                coords.append((sg.x, sg.y))
                
            new_r = dict(r)
            new_r["rute"] = LineString(coords)
            out.append(new_r)
        return out

    slider = widgets.IntSlider(value=15, min=15, max=200, step=5, description="Radius (m):",
                               continuous_update=False, style={"description_width": "initial"},
                               layout=widgets.Layout(width="460px"))
                               
    btn_sim = widgets.Button(description="Simulate", button_style="success", icon="play", layout=widgets.Layout(width="150px"))
    
    step_box = widgets.BoundedFloatText(value=default_step, min=1, max=1000, step=10,
                                        description="Langkah (m):",
                                        style={"description_width": "initial"})
    btn_n = widgets.Button(description="Utara", icon="arrow-up")
    btn_s = widgets.Button(description="Selatan", icon="arrow-down")
    btn_e = widgets.Button(description="Timur", icon="arrow-right")
    btn_w = widgets.Button(description="Barat", icon="arrow-left")

    address_box = widgets.Text(placeholder='Contoh: Jl. Jagir Wonokromo', description='Alamat:', layout=widgets.Layout(width='350px'))
    btn_search = widgets.Button(description="Cari Alamat", button_style="info", icon="search")

    msg = widgets.HTML("")
    
    map_widget = widgets.Image(format='png', layout=widgets.Layout(width='100%', max_width='800px'))
    info_box = widgets.HTML("")

    def refresh():
        zone = get_zone(slider.value)
        p = state["resident"]
        status = status_fn(p, zone)
        routes = get_route(p, zone) if status == "BAHAYA" else []
        
        hit_b, hit_s, n_hit = get_hit_data(slider.value, zone)

        info_box.value = _info_card_html(status, n_hit, len(layers["buildings"]), routes, slider.value)

        plt.ioff() 
        fig, ax = plt.subplots(figsize=(8, 8), dpi=75)
        perfect_routes = fix_route_endpoints(p, routes, layers["shelters"], hit_s)
        
        draw_map(ax, layers, zone, p, perfect_routes,
                 title=f"Skenario luapan {slider.value} m - warga {status}",
                 hit_b=hit_b, hit_s=hit_s)

        buf = io.BytesIO()
        fig.savefig(buf, format='png', bbox_inches='tight')
        buf.seek(0)
        
        plt.close(fig) 
        plt.ion() 
        
        map_widget.value = buf.read()

    def move(dx, dy):
        new_p = move_citizen(state["resident"], dx, dy)
        if not new_p.within(layers["study_area"]):
            msg.value = "<span style='color:#d62828'>Gerakan dibatalkan: keluar dari area studi.</span>"
            return
        msg.value = ""
        state["resident"] = new_p
        refresh() 

    def search_address(_):
        alamat = address_box.value.strip()
        if not alamat:
            msg.value = "<span style='color:#d62828'>Masukkan alamat terlebih dahulu!</span>"
            return
            
        msg.value = "<i>Sedang mencari koordinat, mohon tunggu...</i>"
        try:
            geolocator = Nominatim(user_agent="afl2_evakuasi_app")
            lokasi = geolocator.geocode(alamat + ", Surabaya, Indonesia")
            
            if lokasi:
                x, y = to_utm.transform(lokasi.longitude, lokasi.latitude)
                new_p = Point(x, y)
                if not new_p.within(layers["study_area"]):
                    msg.value = (f"<span style='color:#d62828'>Lokasi ditemukan ({lokasi.address}) "
                                 f"tapi berada di luar batas area studi peta ini.</span>")
                    return
                
                msg.value = f"<span style='color:#2a9d4a'>Berhasil pindah ke: {lokasi.address}</span>"
                state["resident"] = new_p
                refresh() 
            else:
                msg.value = "<span style='color:#d62828'>Alamat tidak ditemukan. Pastikan spesifik.</span>"
        except Exception as e:
            msg.value = f"<span style='color:#d62828'>Gagal mencari alamat, periksa koneksi internetmu.</span>"

    btn_n.on_click(lambda _: move(0, step_box.value))
    btn_s.on_click(lambda _: move(0, -step_box.value))
    btn_e.on_click(lambda _: move(step_box.value, 0))
    btn_w.on_click(lambda _: move(-step_box.value, 0))
    
    btn_search.on_click(search_address)
    btn_sim.on_click(lambda _: refresh())
    
    display(widgets.VBox([
        widgets.HBox([slider, btn_sim]), 
        step_box,
        widgets.HBox([btn_w, btn_n, btn_s, btn_e]),
        widgets.HBox([address_box, btn_search]),
        msg,
        map_widget,
        info_box
    ]))
    refresh()
    
                    
def make_animation(layers, zone_fn, route_fn, resident, r_start=15, r_end=200,
                   n_zone_frames=15, n_walk_frames=20, n_hold_frames=4,
                   save_path="output/evakuasi.gif", fps=5):
    import numpy as np
    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation, PillowWriter
    from shapely.geometry import Point, LineString

    active_layers = layers.copy()
    if "buildings" in active_layers:
        active_layers["buildings"] = active_layers["buildings"].simplify(10)
    if "roads" in active_layers:
        active_layers["roads"] = active_layers["roads"].simplify(10)
    if "rivers" in active_layers:
        active_layers["rivers"] = active_layers["rivers"].simplify(10)

    hit_cache = {}
    def get_hit_data(zone):
        z_id = round(zone.area)
        if z_id not in hit_cache:
            if zone.is_empty:
                hb = np.zeros(len(active_layers["buildings"]), dtype=bool)
                hs = np.zeros(len(active_layers["shelters"]), dtype=bool)
            else:
                hb = active_layers["buildings"].intersects(zone).to_numpy()
                hs = active_layers["shelters"].intersects(zone).to_numpy()
            hit_cache[z_id] = (hb, hs)
        return hit_cache[z_id]

    
    def fix_route_endpoints(res, rts, sh_layers, hs_mask):
        if res is None or not rts:
            return rts or []
        out = []
        safe_shelters = sh_layers[~hs_mask] if hs_mask is not None else sh_layers
        for r in rts:
            rc = [tuple(c[:2]) for c in r["rute"].coords]
            coords = [(res.x, res.y)] + rc
            if not safe_shelters.empty:
                end_pt = Point(rc[-1])
                closest_idx = safe_shelters.distance(end_pt).idxmin()
                sg = safe_shelters.loc[closest_idx].geometry
                coords.append((sg.x, sg.y))
            new_r = dict(r)
            new_r["rute"] = LineString(coords)
            out.append(new_r)
        return out

    frames = []
    for r in np.linspace(r_start, r_end, n_zone_frames):
        frames.append({"zone": zone_fn(r), "resident": resident, "routes": [],
                       "title": f"Luapan naik: {r:.0f} m"})

    final_zone = zone_fn(r_end)
    raw_routes = route_fn(resident, final_zone)
    hb_final, hs_final = get_hit_data(final_zone)
    routes = fix_route_endpoints(resident, raw_routes, active_layers["shelters"], hs_final)
    
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

    plt.ioff()
    fig, ax = plt.subplots(figsize=(8, 8), dpi=60)

    def update(i):
        ax.clear()
        f = frames[i]
        hb, hs = get_hit_data(f["zone"])
        draw_map(ax, active_layers, f["zone"], f["resident"], f["routes"], 
                 title=f["title"], hit_b=hb, hit_s=hs)
        return []

    anim = FuncAnimation(fig, update, frames=len(frames), interval=1000 / fps,
                         blit=False, repeat=False)
    _ensure_dir(save_path)
    anim.save(save_path, writer=PillowWriter(fps=fps), dpi=60)
    
    plt.close(fig)
    plt.ion()
    
    return save_path