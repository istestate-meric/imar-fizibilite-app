import os
import re
import glob
import pdfplumber
import pandas as pd

def imar_pdf_veri_ayristir(pdf_yolu):
    """
    İmar durumu PDF'lerinden Mahalle, Ada, Parsel, KAKS, TAKS, 
    Brüt Alan, Net Konut Alanı ve Terk (Park) alanlarını eksiksiz çeker.
    """
    veri = {
        "Mahalle": "BİLİNMİYOR",
        "Ada": 0,
        "Parsel": 0,
        "İmar Fonksiyonu": "KONUT ALANI",
        "Brüt Tapu Alanı (m²)": 0.0,
        "Net Konut Alanı (m²)": 0.0,
        "Net Konut Oranı (%)": 0.0,
        "Park / Terk Alanı (m²)": 0.0,
        "KAKS": 0.0,
        "TAKS": 0.0
    }
    
    with pdfplumber.open(pdf_yolu) as pdf:
        tam_metin = ""
        for sayfa in pdf.pages:
            metin = sayfa.extract_text()
            if metin:
                tam_metin += metin + "\n"

        # 1. Mahalle Bilgisi (ÇİFTLİK, YAVUZSELİM vb. dinamik çekim)
        mahalle_eslesme = re.search(r"Mahalle\s*\n\s*([A-ZÇĞİÖŞÜa-zçğıöşü\s]+?)(?=\s*Pafta|\s*\n)", tam_metin)
        if mahalle_eslesme:
            veri["Mahalle"] = mahalle_eslesme.group(1).strip()

        # 2. Ada / Parsel
        ada_eslesme = re.search(r"Ada\s*\n\s*(\d+)", tam_metin)
        if ada_eslesme:
            veri["Ada"] = int(ada_eslesme.group(1))

        parsel_eslesme = re.search(r"Parsel\s*\n\s*(\d+)", tam_metin)
        if parsel_eslesme:
            veri["Parsel"] = int(parsel_eslesme.group(1))

        # 3. Brüt Tapu / Grafik Alanı
        brut_eslesme = re.search(r"Alan\s*\*\s*\n\s*([\d\.,]+)\s*m²", tam_metin)
        if brut_eslesme:
            sayi_str = brut_eslesme.group(1).replace(".", "").replace(",", ".")
            veri["Brüt Tapu Alanı (m²)"] = float(sayi_str)

        # 4. KAKS / TAKS Oranları
        kaks_eslesme = re.search(r"Kaks\s*\(Emsal\)\s*\n\s*([\d\.,]+)", tam_metin)
        if kaks_eslesme:
            veri["KAKS"] = float(kaks_eslesme.group(1).replace(",", "."))

        taks_eslesme = re.search(r"Taks\s*\n\s*([\d\.,]+)", tam_metin)
        if taks_eslesme:
            veri["TAKS"] = float(taks_eslesme.group(1).replace(",", "."))

        # 5. Net Konut ve Park/Terk Alanları Ayrımı
        # KONUT ALANI bloğu
        konut_eslesme = re.search(
            r"KONUT ALANI[\s\S]*?Fonksiyon Alanına\s*Giren[\s\S]*?(?:%\s*([\d\.,]+))?[\s\S]*?([\d\.,]+)\s*m²", 
            tam_metin
        )
        if konut_eslesme:
            net_konut_val = float(konut_eslesme.group(2).replace(".", "").replace(",", "."))
            veri["Net Konut Alanı (m²)"] = net_konut_val
            if konut_eslesme.group(1):
                veri["Net Konut Oranı (%)"] = float(konut_eslesme.group(1).replace(",", "."))

        # PARK (Terk) bloğu (Sayfa 2'deki içerik)
        park_eslesme = re.search(
            r"PARK[\s\S]*?Fonksiyon Alanına\s*Giren[\s\S]*?(?:%\s*([\d\.,]+))?[\s\S]*?([\d\.,]+)\s*m²", 
            tam_metin
        )
        if park_eslesme:
            park_val = float(park_eslesme.group(2).replace(".", "").replace(",", "."))
            veri["Park / Terk Alanı (m²)"] = park_val

        # Oran metinden okunamazsa otomatik matematiksel hesaplama
        if veri["Brüt Tapu Alanı (m²)"] > 0:
            if veri["Net Konut Oranı (%)"] == 0.0 and veri["Net Konut Alanı (m²)"] > 0:
                veri["Net Konut Oranı (%)"] = round((veri["Net Konut Alanı (m²)"] / veri["Brüt Tapu Alanı (m²)"]) * 100, 2)

    return veri


def veritabani_tablosunu_olustur(pdf_klasor_yolu="."):
    """
    Klasördeki tüm PDF'leri tarar, düzenler ve arayüz için DataFrame döndürür.
    """
    pdf_dosyalari = glob.glob(os.path.join(pdf_klasor_yolu, "*.pdf"))
    tum_parseller = []

    for pdf in pdf_dosyalari:
        try:
            parsel_verisi = imar_pdf_veri_ayristir(pdf)
            tum_parseller.append(parsel_verisi)
        except Exception as e:
            print(f"Hata ({pdf}): {e}")

    df = pd.DataFrame(tum_parseller)
    
    if not df.empty:
        # Ada ve Parsel sırasına göre dizme
        df = df.sort_values(by=["Ada", "Parsel"]).reset_index(drop=True)
        
    return df

# --- KODU ÇALIŞTIRMA VE SİSTEME YÜKLEME ---
if __name__ == "__main__":
    # PDF'lerin bulunduğu klasör
    df_parseller = veritabani_tablosunu_olustur(".")

    # Ekrandaki tablonun tam karşılığı olan çıktıyı üretir
    print(df_parseller.to_string())

    # Veri tabanınız veya Excel çıktınız için kayıt
    df_parseller.to_excel("Veritabani_Kayıtli_Tum_Parseller.xlsx", index=False)
