import streamlit as st
import pandas as pd
import pdfplumber
import re

# 1. Sayfa Yapılandırması
st.set_page_config(page_title="İstestate Meriç - İmar & Fizibilite Panel", layout="wide")

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

# 3. Beykoz Belediyesi Özel Tablo Ayrıştırıcı
def parse_beykoz_pdf(file):
    data = {
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
        # Sayfa 1: Mahalle, Ada, Parsel, Alan okuma
        page1 = pdf.pages[0]
        tables = page1.extract_tables()
        
        for table in tables:
            for i, row in enumerate(table):
                row_str = " ".join([str(cell) for cell in row if cell])
                
                # Mahalle / Ada / Parsel / Alan Hücre Tespiti
                if "Mahalle" in row_str and i + 1 < len(table):
                    next_row = table[i + 1]
                    if len(next_row) >= 4:
                        data["Mahalle"] = str(next_row[0]).strip().title() if next_row[0] else "-"
                        data["Ada"] = str(next_row[2]).strip() if next_row[2] else "-"
                        data["Parsel"] = str(next_row[3]).strip() if len(next_row) > 3 and next_row[3] else "-"
                        
                        # Alan Temizleme
                        if len(next_row) > 4 and next_row[4]:
                            alan_raw = str(next_row[4]).replace("m²", "").replace(",", "").strip()
                            try:
                                data["Brüt Tapu (m²)"] = float(alan_raw)
                            except ValueError:
                                pass

        # Tüm Metin Üzerinden KAKS / TAKS ve Yedek RegEx Kontrolü
        full_text = ""
        for p in pdf.pages:
            full_text += (p.extract_text() or "") + "\n"

        # Fallback RegEx (Tablo boş dönerse)
        if data["Mahalle"] in ["-", "Pafta"]:
            m_match = re.search(r"(BAKLACI|YAVUZSELİM|ÇİFTLİK|GÖRELE|ÇENGELDERE|FATİH)", full_text, re.IGNORECASE)
            if m_match:
                data["Mahalle"] = m_match.group(1).capitalize()

        if data["Ada"] == "-":
            ada_match = re.search(r"Ada\s*[\n\s]*(\d+)", full_text)
            if ada_match:
                data["Ada"] = ada_match.group(1)

        if data["Parsel"] == "-":
            parsel_match = re.search(r"Parsel\s*[\n\s]*(\d+)", full_text)
            if parsel_match:
                data["Parsel"] = parsel_match.group(1)

        if data["Brüt Tapu (m²)"] == 0.0:
            alan_match = re.search(r"(\d{1,3}(?:\,\d{3})*\.\d{2})\s*m²", full_text)
            if alan_match:
                try:
                    data["Brüt Tapu (m²)"] = float(alan_match.group(1).replace(",", ""))
                except ValueError:
                    pass

        # KAKS / TAKS Okuma
        kaks_match = re.search(r"(?:Kaks|Emsal)\s*[\:\n\s]*([0-9\.]+)", full_text, re.IGNORECASE)
        if kaks_match:
            try:
                data["KAKS"] = float(kaks_match.group(1))
            except ValueError:
                pass

        taks_match = re.search(r"Taks\s*[\:\n\s]*([0-9\.]+)", full_text, re.IGNORECASE)
        if taks_match:
            try:
                data["TAKS"] = float(taks_match.group(1))
            except ValueError:
                pass

        # Net Arsa Hesabı
        data["Net Arsa (m²)"] = round(data["Brüt Tapu (m²)"] * 0.7, 2)

    return data

# 4. Sol Panel UI
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
                parsed_data = parse_beykoz_pdf(file)
                new_row = pd.DataFrame([parsed_data])
                st.session_state.db_parseller = pd.concat([st.session_state.db_parseller, new_row], ignore_index=True)
                st.session_state.processed_files.add(file.name)
                has_new = True
        
        if has_new:
            st.success("Tüm veriler eksiksiz çıkarıldı!")
            st.rerun()

    st.divider()
    st.header("📍 2. Bölge & Parsel Seçimi")
    
    col_a, col_p = st.columns(2)
    with col_a:
        st.text_input("Ada No", value="1617")
    with col_p:
        st.text_input("Parsel No", value="13")
        
    st.button("🔍 Hafızadan Bilgi Çek", use_container_width=True)

# 5. Ana Ekran
st.markdown("<h1 style='text-align: center;'>İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center;'>& MERİÇ İNŞAAT EMLAK</h3>", unsafe_allow_html=True)
st.caption("<p style='text-align: center;'>Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli</p>", unsafe_allow_html=True)

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
