import re
import glob
import pandas as pd
import pdfplumber

def parse_imar_pdf(pdf_path):
    data = {
        "Mahalle": None,
        "Ada": None,
        "Parsel": None,
        "Brut_Tapu_Alani": None,
        "Net_Konut_Alani": None,
        "Konut_Orani_Yuzde": None,
        "Park_Terk_Alani": None,
        "Park_Orani_Yuzde": None,
        "KAKS": None,
        "TAKS": None
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # 1. Mahalle Bilgisi
        mahalle_match = re.search(r"Mahalle\s*\n\s*([A-ZÇĞİÖŞÜ]+)", full_text)
        if mahalle_match:
            data["Mahalle"] = mahalle_match.group(1).strip()
            
        # 2. Ada / Parsel
        ada_match = re.search(r"Ada\s*\n\s*(\d+)", full_text)
        if ada_match:
            data["Ada"] = int(ada_match.group(1))
            
        parsel_match = re.search(r"Parsel\s*\n\s*(\d+)", full_text)
        if parsel_match:
            data["Parsel"] = int(parsel_match.group(1))
            
        # 3. Toplam Brüt Grafik Alanı
        alan_match = re.search(r"Alan\s*\*\s*\n\s*([\d\.,]+)\s*m²", full_text)
        if alan_match:
            val_str = alan_match.group(1).replace(".", "").replace(",", ".")
            data["Brut_Tapu_Alani"] = float(val_str)
            
        # 4. KAKS / TAKS
        kaks_match = re.search(r"Kaks\s*\(Emsal\)\s*\n\s*([\d\.,]+)", full_text)
        if kaks_match:
            data["KAKS"] = float(kaks_match.group(1).replace(",", "."))
            
        taks_match = re.search(r"Taks\s*\n\s*([\d\.,]+)", full_text)
        if taks_match:
            data["TAKS"] = float(taks_match.group(1).replace(",", "."))

        # 5. Konut ve Park Net Alan / Yüzde Hesabı
        # PDF yapısındaki "Fonksiyon Alanına Giren" satırlarını yakalar
        fonksiyon_blocks = re.findall(
            r"(KONUT ALANI|PARK)[\s\S]*?Fonksiyon Alanına\s*Giren[\s\S]*?(?:%\s*([\d\.,]+))?[\s\S]*?([\d\.,]+)\s*m²", 
            full_text
        )
        
        for f_name, pct, area_str in fonksiyon_blocks:
            area_val = float(area_str.replace(".", "").replace(",", "."))
            pct_val = float(pct.replace(",", ".")) if pct else None
            
            if f_name == "KONUT ALANI":
                data["Net_Konut_Alani"] = area_val
                if pct_val:
                    data["Konut_Orani_Yuzde"] = pct_val
            elif f_name == "PARK":
                data["Park_Terk_Alani"] = area_val
                if pct_val:
                    data["Park_Orani_Yuzde"] = pct_val

        # Yüzde bilgisi metinden okunamadıysa Brüt alan üzerinden otomatik hesapla
        if data["Brut_Tapu_Alani"] and data["Brut_Tapu_Alani"] > 0:
            if data["Net_Konut_Alani"] and not data["Konut_Orani_Yuzde"]:
                data["Konut_Orani_Yuzde"] = round((data["Net_Konut_Alani"] / data["Brut_Tapu_Alani"]) * 100, 2)
            if data["Park_Terk_Alani"] and not data["Park_Orani_Yuzde"]:
                data["Park_Orani_Yuzde"] = round((data["Park_Terk_Alani"] / data["Brut_Tapu_Alani"]) * 100, 2)

    return data

# --- Tapan Klasördeki Tüm PDF'leri İşleme ---
pdf_files = glob.glob("*.pdf")  # PDF dosyalarınızın bulunduğu dizin
parsel_listesi = []

for pdf_file in pdf_files:
    try:
        parsed_data = parse_imar_pdf(pdf_file)
        parsel_listesi.append(parsed_data)
    except Exception as e:
        print(f"Hata oluştu ({pdf_file}): {e}")

# DataFrame Dönüştürme ve Sıralama
df = pd.DataFrame(parsel_listesi)
df = df.sort_values(by=["Ada", "Parsel"]).reset_index(drop=True)

# Boş kalan Park alanlarına 0 yazılması
df["Park_Terk_Alani"] = df["Park_Terk_Alani"].fillna(0)
df["Park_Orani_Yuzde"] = df["Park_Orani_Yuzde"].fillna(0)

# Excel Dosyasına Kaydetme
df.to_excel("Guncel_Imar_Durumu_Raporu.xlsx", index=False)

# Sonucu Göster
print(df)
