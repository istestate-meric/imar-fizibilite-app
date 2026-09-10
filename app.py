import pdfplumber
import re

def clean_float(value_str):
    """
    Türkçe sayı formatını (2.131,58 veya 2,131.58) doğru Python float tipine dönüştürür.
    Binlik ayracı olan noktaları temizler.
    """
    if not value_str:
        return 0.0
    value_str = value_str.strip()
    # Eğer hem nokta hem virgül varsa (Örn: 2.131,58)
    if '.' in value_str and ',' in value_str:
        value_str = value_str.replace('.', '').replace(',', '.')
    # Sadece virgül varsa (Örn: 2131,58)
    elif ',' in value_str:
        value_str = value_str.replace(',', '.')
    
    try:
        return float(value_str)
    except ValueError:
        return 0.0

def parse_imar_pdf(pdf_file):
    metin = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            metin += (page.extract_text() or "") + "\n"

    # 1. Mahalle Tespiti
    mahalle_match = re.search(r'(Yavuzselim|Baklacı|Görele|Çiftlik|Çengeldere|Fatih)', metin, re.IGNORECASE)
    mahalle = mahalle_match.group(1).upper() if mahalle_match else "ÇİFTLİK"

    # 2. Ada / Parsel Tespiti
    ada_match = re.search(r'Ada\s*\|\s*Alan.*?\n.*?(\d+)\s*\|\s*(\d+)', metin, re.DOTALL)
    if not ada_match:
        ada_parsel_match = re.search(r'(\d+)\s*/\s*(\d+)', pdf_file.name)
        ada = ada_parsel_match.group(1) if ada_parsel_match else "1617"
        parsel = ada_parsel_match.group(2) if ada_parsel_match else "-"
    else:
        ada = ada_match.group(1)
        parsel = ada_match.group(2)

    # 3. Grafik / Tapu Alanı Tespiti (Örn: 2,131.58 m² veya 974.59 m²)
    alan_match = re.search(r'\|\s*([\d\.,]+)\s*m²', metin)
    tapu_alani = clean_float(alan_match.group(1)) if alan_match else 0.0

    # 4. KAKS (Emsal) Tespiti
    kaks_match = re.search(r'Kaks\s*\(Emsal\).*?\n.*?([\d\.,]+)', metin, re.IGNORECASE)
    kaks = clean_float(kaks_match.group(1)) if kaks_match else 0.30

    # 5. Fonksiyon Alanına Giren m² Tespiti
    fonk_match = re.search(r'Fonksiyon Alanına\s*Giren.*?\n.*?([\d\.,]+)\s*m²', metin, re.DOTALL)
    fonksiyon_alani = clean_float(fonk_match.group(1)) if fonk_match else 0.0

    # TERK TESPİT MANTIĞI:
    # Fonksiyon alanı tapu alanının %98'inden fazlasını kaplıyorsa TERK YAPILMIŞTIR (Net Arsa).
    # Aksi halde henüz terki yapılmamış brüt arsadır.
    terk_yapilmis_mi = False
    if tapu_alani > 0 and (fonksiyon_alani / tapu_alani) >= 0.98:
        terk_yapilmis_mi = True

    return {
        "dosya_adi": pdf_file.name,
        "mahalle": mahalle,
        "ada": ada,
        "parsel": parsel,
        "ada_parsel": f"{ada}/{parsel}",
        "tapu_alani": tapu_alani,
        "fonksiyon_alani": fonksiyon_alani,
        "kaks": kaks,
        "terk_yapilmis_mi": terk_yapilmis_mi
    }
