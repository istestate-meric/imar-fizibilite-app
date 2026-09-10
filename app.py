import streamlit as st
import pandas as pd
import pdfplumber

# 1. Sayfa Yapılandırması
st.set_page_config(page_title="İstestate Meriç - İmar & Fizibilite", layout="wide")

# 2. Session State (Oturum Hafızası) Başlatma
if "db_parseller" not in st.session_state:
    # Sayfa ilk yüklendiğinde varsayılan veri (Görseldeki 1617/13 parseli)
    st.session_state.db_parseller = pd.DataFrame([
        {
            "Mahalle": "Çiftlik",
            "Ada": "1617",
            "Parsel": "13",
            "İmar Fonksiyonu": "KONUT ALANI",
            "Brüt Tapu (m²)": 2131.58,
            "Net Arsa (m²)": 1492.106,
            "Park/Terk (m²)": 0,
            "Terk Statüsü": "Yapılmamış",
            "KAKS": 0.3,
            "TAKS": 0.3
        }
    ])

if "processed_files" not in st.session_state:
    st.session_state.processed_files = set()


# 3. PDF Ayrıştırma Yardımcı Fonksiyonu
def parse_pdf(file):
    """Yüklenen imar durumu PDF dosyasını okuyarak verileri ayıklar."""
    parsed_data = {
        "Mahalle": "-",
        "Ada": "-",
        "Parsel": "-",
        "İmar Fonksiyonu": "-",
        "Brüt Tapu (m²)": 0.0,
        "Net Arsa (m²)": 0.0,
        "Park/Terk (m²)": 0,
        "Terk Statüsü": "Belirtilmemiş",
        "KAKS": 0.0,
        "TAKS": 0.0
    }
    
    with pdfplumber.open(file) as pdf:
        full_text = ""
        for page in pdf.pages:
            full_text += page.extract_text() or ""
            
        # Metin içerisinden temel bilgileri ayıklama mantığı
        lines = full_text.split('\n')
        for line in lines:
            if "Baklacı" in line:
                parsed_data["Mahalle"] = "Baklacı"
            elif "Yavuzselim" in line or "YAVUZSELİM" in line:
                parsed_data["Mahalle"] = "Yavuzselim"
                
            if "KONUT ALANI" in line:
                parsed_data["İmar Fonksiyonu"] = "KONUT ALANI"
                
    return parsed_data


# 4. Sol Panel (Sidebar) UI
with st.sidebar:
    st.header("📋 1. Belge Analizi & Akıllı Hafıza")
    
    # Dosya yükleyici (Görseldeki çoklu seçim alanı)
    uploaded_files = st.file_uploader(
        "İmar Durumu PDF Raporlarını Yükleyin (Çoklu Seçim)",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader"
    )

    # Yeni eklenen dosyaları otomatik işleme ve hafızaya aktarma
    if uploaded_files:
        new_data_added = False
        for file in uploaded_files:
            if file.name not in st.session_state.processed_files:
                parsed_info = parse_pdf(file)
                
                # Yeni veriyi DataFrame'e ekle
                new_row = pd.DataFrame([parsed_info])
                st.session_state.db_parseller = pd.concat([st.session_state.db_parseller, new_row], ignore_index=True)
                
                # İşlenen dosyayı kaydet
                st.session_state.processed_files.add(file.name)
                new_data_added = True
        
        if new_data_added:
            st.success("Yeni raporlar başarıyla analiz edildi ve hafızaya eklendi!")
            st.rerun()

    st.divider()
    st.header("📍 2. Bölge & Parsel Seçimi")
    
    col_ada, col_parsel = st.columns(2)
    with col_ada:
        ada_input = st.text_input("Ada No", value="1617")
    with col_parsel:
        parsel_input = st.text_input("Parsel No", value="13")
        
    st.button("🔍 Hafızadan Bilgi Çek", use_container_width=True)


# 5. Ana Ekran UI
st.title("İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK")
st.subheader("& MERİÇ İNŞAAT EMLAK")
st.caption("Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli")

tab1, tab2, tab3, tab4 = st.tabs([
    "🏗️ İmar & Kapasite Analizi", 
    "📐 Mimari Potansiyel & Havuz Detayı", 
    "💰 Finansal Fizibilite ($ USD)", 
    "🗄️ Sistem Hafızası"
])

with tab4:
    st.markdown("### 🗄️ Veri Tabanında Kayıtlı Tüm Parseller")
    
    # Hafızadaki tüm veriyi tablo olarak sergile
    st.dataframe(
        st.session_state.db_parseller,
        use_container_width=True,
        hide_index=False
    )
