import os
import re
import sqlite3
import pandas as pd
import pdfplumber

# ==========================================
# 1. VERİTABANI VE KURULUM AYARLARI
# ==========================================
DB_NAME = "imar_portfoyu.db"

def init_db():
    """Veritabanı tablosunu oluşturur."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS imar_raporlari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            dosya_adi TEXT,
            mahalle TEXT,
            ada_parsel TEXT,
            tapu_alani REAL,
            terk_durumu TEXT,
            kaks REAL,
            emsal_esas_alan REAL,
            toplam_insaat_alani REAL
        )
    ''')
    conn.commit()
    conn.close()

# ==========================================
# 2. İMAR HESAPLAMA MOTORU
# ==========================================
def hesapla_toplam_insaat_alani(tapu_alani: float, kaks: float, terk_yapilmis_mi: bool):
    """
    Kural Seti:
    - Terk Yapılmış (Net): Tapu Alanı x KAKS x 1.30
    - Terk Yapılmamış (Brüt): Tapu Alanı x 0.70 x KAKS x 1.30
    """
    if terk_yapilmis_mi:
        emsal_esas_alan = tapu_alani
    else:
        emsal_esas_alan = tapu_alani * 0.70
        
    toplam_insaat_alani = emsal_esas_alan * kaks * 1.30
    return round(emsal_esas_alan, 2), round(toplam_insaat_alani, 2)

# ==========================================
# 3. PDF VERİ AYRIŞTIRICI (PARSER)
# ==========================================
def parse_imar_pdf(pdf_path):
    """
    PDF dosyasından Mahalle, Ada/Parsel, Alan, Terk Durumu ve KAKS verilerini çeker.
    """
    metin = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            metin += page.extract_text() or ""

    # 1. Mahalle Tespiti
    mahalle_match = re.search(r'(Yavuzselim|Baklacı|Görele|Çiftlik|Çengeldere|Fatih)', metin, re.IGNORECASE)
    mahalle = mahalle_match.group(1) if mahalle_match else "Belirtilmedi"

    # 2. Ada / Parsel Tespiti (Örn: 2421 / 4)
    ada_parsel_match = re.search(r'(\d+)\s*/\s*(\d+)', metin)
    ada_parsel = f"{ada_parsel_match.group(1)}/{ada_parsel_match.group(2)}" if ada_parsel_match else "Bulunamadı"

    # 3. Tapu Alanı Tespiti (m² cinsinden)
    alan_match = re.search(r'([\d\.,]+)\s*m²', metin)
    if alan_match:
        raw_alan = alan_match.group(1).replace('.', '').replace(',', '.')
        tapu_alani = float(raw_alan)
    else:
        tapu_alani = 0.0

    # 4. KAKS Tespiti
    kaks_match = re.search(r'(?:KAKS|Emsal)\s*[:=]?\s*(0\.\d+|1\.\d+|\d+)', metin, re.IGNORECASE)
    kaks = float(kaks_match.group(1)) if kaks_match else 0.40  # Varsayılan KAKS

    # 5. Terk Yapılmış mı Tespiti (DOP / Terkli / Net vb. ifadelere göre)
    terk_yapilmis_mi = False
    if re.search(r'(terk\s+yapılmış|net\s+arsa|dop\s+kesilmiş|terkli)', metin, re.IGNORECASE):
        terk_yapilmis_mi = True

    return {
        "dosya_adi": os.path.basename(pdf_path),
        "mahalle": mahalle,
        "ada_parsel": ada_parsel,
        "tapu_alani": tapu_alani,
        "kaks": kaks,
        "terk_yapilmis_mi": terk_yapilmis_mi
    }

# ==========================================
# 4. OTOMASYON VE RAPORLAMA AKIŞI
# ==========================================
def klasoru_isle_ve_raporla(pdf_klasor_yolu, cikis_excel_yolu="Imar_Hesaplama_Raporu.xlsx"):
    """
    Belirtilen klasördeki tüm PDF'leri okur, hesaplar, DB'ye kaydeder ve Excel'e aktarır.
    """
    init_db()
    kayitlar = []

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    for dosya in os.listdir(pdf_klasor_yolu):
        if dosya.lower().endswith(".pdf"):
            pdf_yolu = os.path.join(pdf_klasor_yolu, dosya)
            
            # PDF Okuma
            veri = parse_imar_pdf(pdf_yolu)
            
            # Hesaplama
            emsal_esas_alan, toplam_insaat = hesapla_toplam_insaat_alani(
                veri["tapu_alani"], 
                veri["kaks"], 
                veri["terk_yapilmis_mi"]
            )
            
            terk_durumu_str = "Terk Yapılmış (Net)" if veri["terk_yapilmis_mi"] else "Terk Yapılmamış (Brüt)"

            # DB'ye Ekleme
            cursor.execute('''
                INSERT INTO imar_raporlari 
                (dosya_adi, mahalle, ada_parsel, tapu_alani, terk_durumu, kaks, emsal_esas_alan, toplam_insaat_alani)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                veri["dosya_adi"], veri["mahalle"], veri["ada_parsel"], 
                veri["tapu_alani"], terk_durumu_str, veri["kaks"], 
                emsal_esas_alan, toplam_insaat
            ))

            # Rapor Listesine Ekleme
            kayitlar.append({
                "Dosya Adı": veri["dosya_adi"],
                "Mahalle": veri["mahalle"],
                "Ada/Parsel": veri["ada_parsel"],
                "Tapu Alanı (m²)": veri["tapu_alani"],
                "Terk Statüsü": terk_durumu_str,
                "KAKS": veri["kaks"],
                "Emsale Esas Alan (m²)": emsal_esas_alan,
                "Formül": f"{veri['tapu_alani']} x {'1.0' if veri['terk_yapilmis_mi'] else '0.70'} x {veri['kaks']} x 1.30",
                "Toplam İnşaat Alanı (m²)": toplam_insaat
            })

    conn.commit()
    conn.close()

    # Excel Oluşturma
    df = pd.DataFrame(kayitlar)
    df.to_excel(cikis_excel_yolu, index=False)
    print(f"\n[BAŞARILI] {len(kayitlar)} adet rapor işlendi.")
    print(f"[ÇIKTI] Excel dosyası oluşturuldu: {cikis_excel_yolu}")
    print(f"[ÇIKTI] Veriler kaydedildi: {DB_NAME}")
    return df

# ==========================================
# 5. ÇALIŞTIRMA VE TEST
# ==========================================
if __name__ == "__main__":
    # Manuel Test Örneği:
    print("--- Manuel Test Sonuçları ---")
    
    # 1. Yavuzselim 2421/4 (Terki Yapılmış Net Parsel)
    _, test1_sonuc = hesapla_toplam_insaat_alani(tapu_alani=7346.76, kaks=0.45, terk_yapilmis_mi=True)
    print(f"Yavuzselim 2421/4 (Net): {test1_sonuc} m²") # Beklenen: 4,297.85 m²
    
    # 2. Baklacı 1324/9 (Terki Yapılmamış Brüt Parsel)
    _, test2_sonuc = hesapla_toplam_insaat_alani(tapu_alani=22709.72, kaks=0.40, terk_yapilmis_mi=False)
    print(f"Baklacı 1324/9 (Brüt): {test2_sonuc} m²")   # Beklenen: 8,266.34 m²

    # PDF Klasör Otomasyonunu Çalıştırmak İçin (Yolu kendi klasörünüze göre güncelleyin):
    # klasoru_isle_ve_raporla(pdf_klasor_yolu="./imar_pdf_klasoru")
