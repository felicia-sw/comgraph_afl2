"""
main.py

Pipeline Runner dan Validasi Layer Spasial Luapan Kali Jagir.
Menjalankan integrasi layer spasial, transformasi koordinat (CRS),
dan simulasi buffer bahaya luapan.
"""

import sys
import src.data_layers as dl

def main():
    print("=" * 70)
    print("SIMULASI SKENARIO LUAPAN KALI JAGIR & ANALISIS KANDIDAT SHELTER")
    print("Mata Kuliah: Grafika Komputer & GIS - Universitas Ciputra")
    print("Penanggung Jawab Data & CRS: ORANG 1")
    print("=" * 70)

    print("\n[1/3] Memuat dan mentransformasi seluruh layer ke EPSG:32749...")
    layers = dl.load_all_layers()
    print("  -> Seluruh layer berhasil dimuat dan terproyeksi ke UTM Zone 49S.")

    print("\n[2/3] Memvalidasi integritas data spasial (Checklist Evaluasi):")
    val_table = dl.validate_layers(layers)
    print(val_table.to_string(index=False))

    print("\nBreakdown Shelter Berdasarkan Jenis:")
    print(layers["shelters"]["amenity"].value_counts().to_string())
    print(f"Total Kapasitas Seluruh Shelter: {layers['shelters']['kapasitas'].sum():,} jiwa")

    print("\n[3/3] Menghitung Analisis Skenario Luapan Multi-Radius:")
    scenarios = [15, 50, 100, 200]
    summary_table = dl.generate_scenario_summary(
        layers["buildings"],
        layers["shelters"],
        layers["jagir_water"],
        layers["study_area"],
        scenarios=scenarios
    )
    print(summary_table.to_string(index=False))

    print("\n" + "=" * 70)
    print("VALIDASI BERHASIL! Data siap digunakan di notebook 'flood_evacuation.ipynb'")
    print("=" * 70)

if __name__ == "__main__":
    main()
