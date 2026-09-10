import pdfplumber
import re

def clean_float(value_str):
    """Sayı ifadelerini temizler ve float tipine çevirir."""
    if not value_str:
        return 0.0
    # Sadece rakam, nokta ve virgülleri tut
    cleaned = re.sub(r'[^\d.,]', '', str(value_str)).strip()
    if not cleaned:
        return 0.0
    
    # Format dönüşümü
    if '.' in cleaned and ',' in cleaned:
        cleaned = cleaned.replace('.', '').replace(',', '.')
    elif ',' in cleaned:
        cleaned = cleaned.replace(',', '.')
    
    try:
        return float(cleaned)
    except ValueError:
        return 0.0

def parse_imar_pdf(pdf_file):
    metin = ""
    try:
        with pdfplumber.open(pdf_file) as pdf:
            for page in pdf.pages:
                metin += (page.extract_text() or "") + "\n"
    except Exception:
        metin = ""

    # 1. Mahalle Tespiti
    mahalle_match = re.search(r'(Yavuzselim|Baklacı|Görele|Çiftlik|Çengeldere|Fatih)', metin, re.IGNORECASE)
    mahalle = mahalle_match.group(1).upper() if mahalle_match else "ÇİFTLİK"

    # 2. Ada / Parsel Tespiti
    # Öncelik: Dosya adından okuma (En güvenli yöntem)
    # Örn: "1617 Ada 13 Parsel.pdf" -> Ada: 1617, Parsel: 13
    filename_match = re.search(r'(\d+)\s*Ada\s*(\d+)\s*Parsel', pdf_file.name, re.IGNORECASE)
    if filename_match:
        ada = filename_match.group(1)
        parsel = filename_match.group(2)
    else:
        # Metin içi alternatif arama
        ada_match = re.search(r'Ada\s*:\s*(\d+)', metin, re.IGNORECASE)
        parsel_match = re.search(r'Parsel\s*:\s*(\d+)', metin, re.IGNORECASE)
        ada = ada_match.group(1) if ada_match else "1617"
        parsel = parsel_match.group(1) if parsel_match else "-"

    # 3. Tapu Alanı / Grafik Alanı Tespiti
    # 'm²' veya 'm2' önündeki veya 'Alan' etiketinin karşısındaki ilk sayıyı yakalar
    tapu_alani = 0.0
    alan_patterns = [
        r'(?:Tapu|Grafik|Alan|Yüzölçüm)[^\d\n]*([\d\.,]+)\s*(?:m²|m2)?',
        r'([\d\.,]+)\s*(?:m²|m2)'
    ]
    for pattern in alan_patterns:
        match = re.search(pattern, metin, re.IGNORECASE)
        if match:
            val = clean_float(match.group(1))
            if val > 0:
                tapu_alani = val
                break

    # 4. Fonksiyon Alanı Tespiti
    fonksiyon_alani = 0.0
    fonk_match = re.search(r'Fonksiyon[^\d\n]*([\d\.,]+)', metin, re.IGNORECASE)
    if fonk_match:
        fonksiyon_alani = clean_float(fonk_match.group(1))

    # 5. KAKS / Emsal Tespiti
    kaks = 0.30
    kaks_match = re.search(r'(?:KAKS|Emsal)[^\d\n]*([\d\.,]+)', metin, re.IGNORECASE)
    if kaks_match:
        val = clean_float(kaks_match.group(1))
        if val > 0:
            kaks = val

    # Terk Statüsü Hesabı (%98 üzeri net alan kabul edilir)
    terk_yapilmis_mi = False
    if tapu_alani > 0 and fonksiyon_alani > 0:
        if (fonksiyon_alani / tapu_alani) >= 0.98:
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
