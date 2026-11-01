# Simulasi Skenario Bahaya Luapan Kali Jagir dan Evakuasi Interaktif di Kawasan Pintu Air Jagir, Wonokromo, Surabaya

**Mata Kuliah:** Graphic Computer (AFL 2)  
**Program Studi:** Informatika, Universitas Ciputra Surabaya  

---

## 1. Deskripsi Proyek

Proyek ini membangun sistem simulasi spasial modular dan grafika komputer 2D berbasis Python dan Jupyter Notebook (`flood_evacuation.ipynb`) untuk memodelkan dampak luapan air sungai **Kali Jagir** (kawasan Pintu Air Jagir, Wonokromo, Surabaya) serta rute evakuasi warga menuju titik penampungan aman (*evacuation shelter*).

Seluruh data diunduh satu kali dari OpenStreetMap (OSM) dan disimpan secara offline pada direktori `data/`, sehingga notebook dan modul analisis dapat berjalan sepenuhnya tanpa ketergantungan koneksi internet.

---

## 2. Parameter Spasial & Sistem Koordinat (CRS)

- **Area Kajian Inti (Core Study Area):**
  - Bujur Timur (BT): $112.728^{\circ} - 112.760^{\circ}$
  - Lintang Selatan (LS): $-7.312^{\circ} - -7.292^{\circ}$
  - Luas Area: $\approx 7.8\text{ km}^2$ di sekitar Pintu Air Jagir, Wonokromo, Surabaya.
- **Buffer Padding Unduhan:** Data diunduh dengan penambahan jarak batas (*padding*) sebesar $500\text{ m}$ agar jaringan jalan dan aliran sungai tidak terpotong di tepi area, sedangkan kalkulasi statistik difokuskan pada area inti studi.
- **Sistem Koordinat Sumber (Source CRS):** `EPSG:4326` (WGS 84, derajat geografis).
- **Sistem Koordinat Analisis (Analysis CRS):** `EPSG:32749` (WGS 84 / UTM Zone 49S, satuan meter).
- **Aturan Ketat Geodesi:** Seluruh operasi geometri metrik (`.buffer()`, `.area`, `.distance()`) wajib dilakukan pada layer yang telah ditransformasikan ke `EPSG:32749`.

---

## 3. Empat Layer Spasial Utama

1. **Layer 1: Kali Jagir (`LineString` & `Polygon`)**
   - 3 segmen garis aliran sungai Kali Jagir ($\approx 2.5\text{ km}$ di dalam area inti) dan poligon badan air (`natural=water`).
   - Sesuai **Permen PUPR No. 28/PRT/M/2015**, zona sempadan dan bahaya luapan diukur langsung dari **tepi luar poligon badan air sungai**, bukan sekadar poros garis tengah sungai.
2. **Layer 2: Tapak Bangunan Warga (`Polygon`)**
   - $\approx 36.260$ poligon tapak bangunan warga di dalam area inti studi dengan identitas unik (`id`, `name`, `building`).
3. **Layer 3: Titik Fasilitas Evakuasi / Shelter (`Point`)**
   - Fasilitas umum bertipe `amenity`: `place_of_worship`, `school`, `college`, `university`.
   - Hasil kueri fasilitas shelter pada batas koordinat area inti (*core bounding box* tanpa *padding*) menghasilkan 114 objek mentah. Setelah dilakukan pemotongan spasial ke poligon area studi inti, 3 objek dengan *centroid* di luar batas dieksklusi sehingga menghasilkan tepat **111 titik shelter** (55 tempat ibadah, 47 sekolah, 9 kampus perguruan tinggi).
   - **Kapasitas Ruang Pengungsi:** Sesuai standar **Perka BNPB No. 7/2008** ($3\text{ m}^2/\text{jiwa}$), kapasitas dihitung dari **luas tapak bangunan aktual** di dalam batas poligon/lahan shelter menggunakan operasi tumpang-tindih geometri (`gpd.overlay(..., how='intersection')`):
     $$\text{Kapasitas} = \left\lfloor \frac{\text{Luas Tapak Bangunan Aktual } (m^2)}{3} \right\rfloor$$
     Total kapasitas terpasang dari 111 fasilitas shelter ini mencapai **38.230 jiwa**.
   - **Asumsi Fasilitas Titik Murni:** Dari 111 shelter, terdapat 3 fasilitas bertipe titik murni di OSM yang tidak memiliki batas poligon bangunan (Telkom University Surabaya, Gereja Katolik Santo Yohanes Pemandi, dan GPdI Bukit Zaitun). Untuk ketiga fasilitas ini, diasumsikan luas tapak bangunan minimum standar sebesar $150\text{ m}^2$ ($\approx 50\text{ jiwa}$ sesuai standar $3\text{ m}^2/\text{jiwa}$).
4. **Layer 4: Jaringan Jalan Pejalan Kaki (`LineString` & NetworkX Graph)**
   - Jaringan jalan pedestrian (`network_type="walk"`) terproyeksi ke `EPSG:32749` ($3.634$ simpul, $9.770$ ruas jalan).

---

## 4. Skenario Bahaya Luapan Kali Jagir

Sesuai Proposal Bab 1.2 dan 2.2, simulasi bahaya luapan Kali Jagir dimodelkan menggunakan penyanggaan spasial (*buffer*) metrik bertingkat dari poligon tepi badan air Kali Jagir:

1. **Skenario 15 m (Sempadan Minimum PUPR):**
   Berdasarkan Permen PUPR No. 28/PRT/M/2015, sempadan minimum sungai perkotaan tidak bertanggul adalah 15 m. Skenario ini memodelkan luapan dasar dengan genangan seluas $14,73\text{ ha}$, berdampak pada 244 bangunan warga ($0,67\%$, luas tapak $11.359,9\text{ m}^2$). Seluruh 111 shelter berada dalam kondisi aman (kapasitas $38.230\text{ jiwa}$).
2. **Skenario 100 m (Luapan Hipotetis Sedang):**
   Memodelkan kenaikan debit air yang meluap hingga radius 100 m dari badan air (luas genangan $53,09\text{ ha}$). Sebanyak 1.793 bangunan terdampak ($4,94\%$, luas tapak $128.762,0\text{ m}^2$) dan 6 shelter tergenang, menyisakan 105 shelter aman (kapasitas $37.727\text{ jiwa}$).
3. **Skenario 200 m (Luapan Hipotetis Besar):**
   Memodelkan skenario bencana ekstrem luapan hingga radius 200 m (luas genangan $101,12\text{ ha}$). Sebanyak 3.731 bangunan terdampak ($10,29\%$, luas tapak $287.393,1\text{ m}^2$) dan 10 shelter tergenang, menyisakan 101 shelter aman (kapasitas $36.858\text{ jiwa}$).

---

## 5. Pembagian Peran Tim & Arsitektur Git

Proyek ini dibangun secara terintegrasi oleh 3 peran (*Orang*):

| Peran | Penanggung Jawab | Fokus & Tanggung Jawab Utama | Berkas Utama |
|---|---|---|---|
| **ORANG 1** | *Data Engineer & Lead Integrator* | Pengunduhan data OSM, transformasi CRS metrik, penyiapan layer, pemotongan area inti, buffer sempadan banjir Kali Jagir, spatial join, tabel skenario, serta integrasi notebook. | `src/fetch_data.py`, `src/data_layers.py`, `flood_evacuation.ipynb`, `requirements.txt`, `README.md` |
| **ORANG 2** | *Analysis & Routing Specialist* | Matriks translasi koordinat homogen 2D (Week 3), uji status bahaya warga *Point-in-Polygon* (`within`), eliminasi jalan tergenang (*subgraph* jalan kering), dan perutean rute terpendek Dijkstra. | `src/analysis.py` |
| **ORANG 3** | *Graphics & Interactive Specialist* | Hirarki urutan *rendering* grafika komputer (*Z-order*), visualisasi peta kartografis & legenda multi-layer, kontrol interaktif `ipywidgets`, dan animasi interpolasi Bézier linear ke file GIF. | `src/graphics.py`, `output/` |

### Struktur Direktori Repositori:
```text
├── data/                            # Berkas cache lokal OSM (offline)
│   ├── core_bbox.geojson            # Poligon area inti studi
│   ├── kali_jagir_lines.geojson     # Layer 1A: Garis aliran sungai
│   ├── kali_jagir_water_poly.geojson# Layer 1B: Poligon badan air sungai
│   ├── buildings.geojson            # Layer 2: Tapak bangunan warga
│   ├── shelters_raw.geojson         # Layer 3: Fasilitas umum shelter
│   └── walk_network.graphml         # Layer 4: Jaringan jalan pejalan kaki
├── output/                          # Berkas luaran visualisasi & animasi
│   └── peta_skenario.png            # Peta komparasi multi-skenario luapan (15 m, 100 m, 200 m)
├── src/
│   ├── __init__.py                  # Inisialisasi paket Python
│   ├── fetch_data.py                # Skrip pengunduh data OSM satu kali
│   ├── data_layers.py               # [Orang 1] Modul pemrosesan data & spatial join
│   ├── analysis.py                  # [Orang 2] Modul translasi 2D & routing jalan kering
│   └── graphics.py                  # [Orang 3] Modul kartografi, widget, dan animasi
├── flood_evacuation.ipynb           # Notebook orkestrator interaktif utama
├── main.py                          # Skrip pengujian CLI pipeline spasial
├── requirements.txt                 # Dependensi pustaka Python
└── README.md                        # Dokumentasi proyek
```

---

## 6. Cara Instalasi & Menjalankan

### A. Persiapan Lingkungan Virtual (Virtual Environment)
```bash
# Membuat virtual environment
python -m venv venv

# Mengaktifkan environment di Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Menginstal dependensi:
pip install -r requirements.txt
```

### B. Menguji Validasi Layer & Pipeline Spasial (CLI)
```bash
python main.py
```

### C. Menjalankan Simulasi Interaktif di Jupyter Notebook
```bash
jupyter notebook flood_evacuation.ipynb
```

---

## 7. Lisensi Data
Sumber data geografis berasal dari **© OpenStreetMap contributors** di bawah lisensi *Open Database License (ODbL)*.
