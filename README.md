# comgraph_afl2

Simulasi skenario bahaya luapan Kali Jagir dan evakuasi interaktif di Kecamatan Wonokromo, Surabaya.
Computer Graphics AFL 2, Universitas Ciputra.

## Isi

| File | Fungsi |
|---|---|
| `flood_evacuation.ipynb` | Notebook utama: 4 layer, 4 operasi GIS, peta, kontrol interaktif, animasi |
| `fetch_data.py` | Mengunduh data OpenStreetMap satu kali ke folder `data/` |
| `data/` | Layer sungai, badan air, bangunan, shelter (GeoJSON) dan jaringan jalan (GraphML) |
| `output/` | Hasil: `peta_skenario.png` dan `animasi_evakuasi.gif` |

## Menjalankan

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
jupyter notebook flood_evacuation.ipynb
```

Data sudah ada di `data/`, jadi notebook bisa jalan tanpa internet.
Untuk mengunduh ulang: hapus isi `data/` lalu jalankan `python fetch_data.py`.

## Layer dan operasi GIS

- Layer: Kali Jagir (garis + poligon air), bangunan (poligon), shelter (titik), jaringan jalan (graf)
- Operasi: transformasi CRS + buffer, spatial join (`intersects`), point-in-polygon (`within`), rute terpendek di jalan kering
- Grafika komputer: matriks translasi homogen (Week 3), kurva Bézier linear untuk animasi (Week 2), urutan render dan legenda (Week 5)

## Sumber data

© OpenStreetMap contributors, lisensi ODbL. Area studi 112,728–112,760 BT dan 7,292–7,312 LS.
