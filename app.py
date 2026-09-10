import streamlit as st
import pandas as pd
import pdfplumber
import re

# 1. Sayfa Yapılandırması
st.set_page_config(page_title="İstestate Meriç - İmar & Fizibilite Panel", layout="wide")

# CSS ile Arayüz Tasarımını Düzeltme
st.markdown("""
    <style>
    .main-header { font-size: 26px; font-weight: bold; color: #FFFFFF; text-align: center; }
    .sub-header { font-size: 20px; font-weight: bold; color: #31333F; text-align: center; }
    </style>
""", unsafe_allow_html=True)

# 2. Session State Başlatma
if "db_parseller" not in st.session_state:
    st.session_state.db_parseller = pd.DataFrame([
        {
            "Mahalle": "Çiftlik",
            "Ada": "1617",
            "Parsel": "13",
            "İmar Fonksiyonu": "KONUT ALANI",
            "Brüt Tapu (m²)": 2131.58,
            "Net Arsa (m²)": 1492.106,
            "Park/Terk (m²)": 0.0,
            "Terk Statüsü": "Yapılmamış",
            "KAKS": 0.3,
            "TAKS": 0.3
        }
    ])

if "processed_files" not in st.session_state:
    st.session_state.processed_files = set()

# 3. İmar PDF Ayrıştırma Motoru (Gelişmiş Regex & Tablo Algılama)
def parse_imar_pdf(file):
    parsed = {
        "Mahalle": "-",
        "Ada": "-",
        "Parsel": "-",
        "İmar Fonksiyonu": "KONUT ALANI",
        "Brüt Tapu (m²)": 0.0,
        "Net Arsa (m²)": 0.0,
        "Park/Terk (m²)": 0.0,
        "Terk Statüsü": "Belirtilmemiş",
        "KAKS": 0.0,
        "TAKS": 0.0
    }
    
    with pdfplumber.open(file) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += (page.extract_text() or "") + "\n"

    # Mahalle Tespiti
    mahalle_match = re.search(r"Mahalle\s*[\|\:]?\s*([A-ZÇĞİÖŞÜa-zçğiöşü]+)", full_text)
    if mahalle_match:
        parsed["Mahalle"] = mahalle_match.group(1).title()

    # Ada / Parsel Tespiti
    ada_match = re.search(r"Ada\s*[\|\:]?\s*(\d+)", full_text)
    if ada_match:
        parsed["Ada"] = ada_match.group(1)
        
    parsel_match = re.search(r"Parsel\s*[\|\:]?\s*(\d+)", full_text)
    if parsel_match:
        parsed["Parsel"] = parsel_match.group(1)

    # Toplam Grafik Alanı (Brüt) Tespiti (Örn: 22,709.72 m²)
    alan_match = re.search(r"Alan\s*\*?\s*[\|\:]?\s*([\d\.\,]+)\s*m²", full_text)
    if alan_match:
        val_str = alan_match.group(1).replace(",", "")
        try:
            parsed["Brüt Tapu (m²)"] = float(val_str)
        except ValueError:
            pass

    # KAKS / TAKS Tespiti
    kaks_match = re.search(r"Kaks\s*\(Emsal\)\s*[\n\s]*([\d\.]+)", full_text, re.IGNORECASE)
    if kaks_match:
        try:
            parsed["KAKS"] = float(kaks_match.group(1))
        except ValueError:
            pass

    taks_match = re.search(r"Taks\s*[\n\s]*([\d\.]+)", full_text, re.IGNORECASE)
    if taks_match:
        try:
            parsed["TAKS"] = float(taks_match.group(1))
        except ValueError:
            pass

    # Net Arsa Hesaplaması (Eğer KAKS varsa Brüt x 0.7 varsayımı veya doğrudan okuma)
    parsed["Net Arsa (m²)"] = round(parsed["Brüt Tapu (m²)"] * 0.7, 2)
    
    return parsed

# 4. Sol Menü (Sidebar)
with st.sidebar:
    st.header("📜 1. Belge Analizi & Akıllı Hafıza")
    
    uploaded_files = st.file_uploader(
        "İmar Durumu PDF Raporlarını Yükleyin (Çoklu Seçim)",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader"
    )

    if uploaded_files:
        has_new = False
        for file in uploaded_files:
            if file.name not in st.session_state.processed_files:
                data = parse_imar_pdf(file)
                new_df = pd.DataFrame([data])
                st.session_state.db_parseller = pd.concat([st.session_state.db_parseller, new_df], ignore_index=True)
                st.session_state.processed_files.add(file.name)
                has_new = True
        
        if has_new:
            st.success("Yeni imar raporları başarıyla işlendi!")
            st.rerun()

    st.divider()
    st.header("📍 2. Bölge & Parsel Seçimi")
    
    col_a, col_p = st.columns(2)
    with col_a:
        st.text_input("Ada No", value="1617")
    with col_p:
        st.text_input("Parsel No", value="13")
        
    st.button("🔍 Hafızadan Bilgi Çek", use_container_width=True)

# 5. Ana Sayfa Başlıkları
st.markdown("<h1 style='text-align: center;'>İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; color: #0083B0;'>& MERİÇ İNŞAAT EMLAK</h3>", unsafe_allow_html=True)
st.caption("<p style='text-align: center;'>Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli</p>", unsafe_allow_html=True)

# 6. Sekmeler (Tabs)
tab1, tab2, tab3, tab4 = st.tabs([
    "🏗️ İmar & Kapasite Analizi", 
    "📐 Mimari Potansiyel & Havuz Detayı", 
    "💰 Finansal Fizibilite ($ USD)", 
    "🗄️ Sistem Hafızası"
])

with tab4:
    st.subheader("🗄️ Veri Tabanında Kayıtlı Tüm Parseller")
    st.dataframe(
        st.session_state.db_parseller,
        use_container_width=True,
        hide_index=True
    )
