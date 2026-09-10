import streamlit as st
import pandas as pd
import pdfplumber
import re
import io

# Sayfa Yapılandırması
st.set_page_config(
    page_title="İmar Durumu ve İnşaat Alanı Hesaplayıcı",
    page_icon="🏗️",
    layout="wide"
)

# ==========================================
# 1. İMAR HESAPLAMA MOTORU
# ==========================================
def hesapla_toplam_insaat_alani(tapu_alani: float, kaks: float, terk_yapilmis_mi: bool):
    """
    Formül Kuralı:
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
# 2. PDF VERİ AYRIŞTIRICI
# ==========================================
def parse_imar_pdf(pdf_file):
    metin = ""
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            metin += page.extract_text() or ""

    # Mahalle Tespiti
    mahalle_match = re.search(r'(Yavuzselim|Baklacı|Görele|Çiftlik|Çengeldere|Fatih)', metin, re.IGNORECASE)
    mahalle = mahalle_match.group(1) if mahalle_match else "Belirtilmedi"

    # Ada / Parsel Tespiti
    ada_parsel_match = re.search(r'(\d+)\s*/\s*(\d+)', metin)
    ada_parsel = f"{ada_parsel_match.group(1)}/{ada_parsel_match.group(2)}" if ada_parsel_match else "Bulunamadı"

    # Tapu Alanı Tespiti
    alan_match = re.search(r'([\d\.,]+)\s*m²', metin)
    if alan_match:
        raw_alan = alan_match.group(1).replace('.', '').replace(',', '.')
        tapu_alani = float(raw_alan)
    else:
        tapu_alani = 0.0

    # KAKS Tespiti
    kaks_match = re.search(r'(?:KAKS|Emsal)\s*[:=]?\s*(0\.\d+|1\.\d+|\d+)', metin, re.IGNORECASE)
    kaks = float(kaks_match.group(1)) if kaks_match else 0.40

    # Terk Yapılmış mı Tespiti
    terk_yapilmis_mi = False
    if re.search(r'(terk\s+yapılmış|net\s+arsa|dop\s+kesilmiş|terkli)', metin, re.IGNORECASE):
        terk_yapilmis_mi = True

    return {
        "dosya_adi": pdf_file.name,
        "mahalle": mahalle,
        "ada_parsel": ada_parsel,
        "tapu_alani": tapu_alani,
        "kaks": kaks,
        "terk_yapilmis_mi": terk_yapilmis_mi
    }

# ==========================================
# 3. STREAMLIT ARAYÜZÜ
# ==========================================
st.title("🏗️ Beykoz Bölgesi İmar & İnşaat Alanı Otomasyonu")
st.markdown("PDF formatındaki imar durum raporlarını yükleyerek toplam inşaat alanı hesaplamalarını otomatik gerçekleştirebilirsiniz.")

tab1, tab2 = st.tabs(["📄 Toplu PDF İşleme", "✏️ Manuel Hesaplama"])

# --- TAB 1: PDF YÜKLEME VE OTOMASYON ---
with tab1:
    uploaded_files = st.file_uploader(
        "İmar Durumu PDF Belgelerini Yükleyin", 
        type=["pdf"], 
        accept_multiple_files=True
    )

    if uploaded_files:
        sonuclar = []
        for file in uploaded_files:
            parsed = parse_imar_pdf(file)
            emsal_esas, toplam_insaat = hesapla_toplam_insaat_alani(
                parsed["tapu_alani"], 
                parsed["kaks"], 
                parsed["terk_yapilmis_mi"]
            )
            
            sonuclar.append({
                "Dosya Adı": parsed["dosya_adi"],
                "Mahalle": parsed["mahalle"],
                "Ada/Parsel": parsed["ada_parsel"],
                "Tapu Alanı (m²)": parsed["tapu_alani"],
                "Terk Statüsü": "Terk Yapılmış (Net)" if parsed["terk_yapilmis_mi"] else "Terk Yapılmamış (Brüt)",
                "KAKS": parsed["kaks"],
                "Emsale Esas Alan (m²)": emsal_esas,
                "Formül": f"{parsed['tapu_alani']} x {'1.0' if parsed['terk_yapilmis_mi'] else '0.70'} x {parsed['kaks']} x 1.30",
                "Toplam İnşaat Alanı (m²)": toplam_insaat
            })

        df = pd.DataFrame(sonuclar)
        
        st.subheader("Hesaplama Sonuçları")
        st.dataframe(df, use_container_width=True)

        # Excel İndirme Butonu
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='İmar Hesaplama')
        excel_data = output.getvalue()

        st.download_button(
            label="📥 Sonuçları Excel Olarak İndir",
            data=excel_data,
            file_name="Imar_Hesaplama_Raporu.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# --- TAB 2: MANUEL HESAPLAMA ---
with tab2:
    st.subheader("Hızlı Manuel Parser")
    col1, col2 = st.columns(2)
    
    with col1:
        tapu_alani_input = st.number_input("Tapu Alanı (m²)", min_value=0.0, value=1000.0, step=50.0)
        kaks_input = st.number_input("KAKS (Emsal)", min_value=0.0, max_value=3.0, value=0.40, step=0.05)
    
    with col2:
        terk_input = st.radio("Terk Durumu", ["Terk Yapılmamış (Brüt Arazi)", "Terk Yapılmış (Net Arazi)"])
        is_terk = True if "Net" in terk_input else False

    emsal_m2, insaat_m2 = hesapla_toplam_insaat_alani(tapu_alani_input, kaks_input, is_terk)
    
    st.info(f"**Uygulanan Formül:** {tapu_alani_input} × {'1.0' if is_terk else '0.70'} × {kaks_input} × 1.30")
    
    col_res1, col_res2 = st.columns(2)
    col_res1.metric("Emsale Esas Alan", f"{emsal_m2:,.2f} m²")
    col_res2.metric("Toplam İnşaat Alanı (x1.30)", f"{insaat_m2:,.2f} m²")
