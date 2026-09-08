import io
import json
import re
import sqlite3
import urllib.request
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
import pdfplumber
import google.generativeai as genai

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Sayfa Yapılandırması
st.set_page_config(
    page_title="İstestate Meriç - İmar & Fizibilite Portalı", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# SİSTEM HAFIZASI & BEYKOZ MAHALLE LİSTESİ (45 MAHALLE)
# ---------------------------------------------------------
MAHALLE_LISTESI = [
    "AKBABA", "ALİBAHADIR", "ANADOLU HİSARI", "ANADOLU KAVAĞI", "ANADOLUFENERİ",
    "BAKLACI", "BEYKOZ MERKEZ", "BOZHANE", "ÇAMLIBAHÇE", "ÇENGELDERE",
    "ÇİFTLİK", "ÇİĞDEM", "ÇUBUKLU", "CUMHURİYET", "DERESEKİ",
    "ELMALI", "FATİH", "GÖKSU", "GÖLLÜ", "GÖRELE",
    "GÖZTEPE", "GÜMÜŞSUYU", "İNCİRKÖY", "İSHAKLI", "KANLICA",
    "KAVACIK", "KAYNARCA", "KILIÇLI", "MAHMUTŞEVKETPAŞA", "ÖĞÜMCE",
    "ÖRNEKKÖY", "ORTAÇEŞME", "PAŞABAHÇE", "PAŞAMANDIRA", "POLONEZKÖY",
    "POYRAZKÖY", "RİVA", "RÜZGARLIBAHÇE", "SOĞUKSU", "TOKATKÖY",
    "YALIKÖY", "YAVUZ SELİM", "YENİ MAHALLE", "ZERZEVATÇI"
]

def init_db():
    conn = sqlite3.connect("imar_hafizasi.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS imar_kayitlari (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mahalle TEXT,
            ada TEXT,
            parsel TEXT,
            tapu_alani REAL,
            kaks REAL,
            taks REAL,
            UNIQUE(mahalle, ada, parsel)
        )
    """)
    conn.commit()
    conn.close()

init_db()

def db_kayit_ekle_veya_guncelle(mahalle, ada, parsel, tapu_alani, kaks, taks):
    conn = sqlite3.connect("imar_hafizasi.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO imar_kayitlari (mahalle, ada, parsel, tapu_alani, kaks, taks)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(mahalle, ada, parsel) DO UPDATE SET
            tapu_alani=excluded.tapu_alani,
            kaks=excluded.kaks,
            taks=excluded.taks
    """, (str(mahalle).upper(), str(ada), str(parsel), float(tapu_alani), float(kaks), float(taks)))
    conn.commit()
    conn.close()

def db_kayit_sorgula(mahalle, ada, parsel):
    conn = sqlite3.connect("imar_hafizasi.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT tapu_alani, kaks, taks FROM imar_kayitlari 
        WHERE upper(mahalle) = upper(?) AND ada = ? AND parsel = ?
    """, (str(mahalle), str(ada), str(parsel)))
    result = cursor.fetchone()
    conn.close()
    return result

def db_mahalleleri_getir():
    conn = sqlite3.connect("imar_hafizasi.db")
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT mahalle FROM imar_kayitlari")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows if r[0]]

# ---------------------------------------------------------
# CSS VE DİĞER YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------
st.markdown("""
<style>
    .main { background-color: #0F172A; }
    section[data-testid="stSidebar"] { background-color: #1E293B !important; border-right: 1px solid #334155; }
    div[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 700 !important; color: #38BDF8 !important; }
    div[data-testid="stMetric"] { background-color: #1E293B; border: 1px solid #334155; border-radius: 10px; padding: 15px; }
    .stTabs [data-baseweb="tab"] { background-color: #1E293B; border-radius: 8px 8px 0px 0px; padding: 10px 20px; color: #94A3B8; border: 1px solid #334155; }
    .stTabs [aria-selected="true"] { background-color: #2563EB !important; color: #FFFFFF !important; border-color: #2563EB !important; }
    .stDownloadButton > button { width: 100%; background-color: #059669 !important; color: white !important; font-weight: 600 !important; border-radius: 8px !important; padding: 12px 24px !important; border: none !important; }
</style>
""", unsafe_allow_html=True)

@st.cache_data(ttl=3600)
def get_tcmb_usd_rate():
    try:
        url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            tree = ET.parse(response)
            root = tree.getroot()
            for currency in root.findall('Currency'):
                if currency.get('CurrencyCode') == 'USD':
                    forex_buying = currency.find('ForexBuying').text
                    return float(forex_buying)
    except Exception:
        return 34.50

@st.cache_data(ttl=1800)
def fetch_market_prices_via_gemini(mahalle_adi, tipoloji, api_key):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.6-flash')
        
        prompt = f"""
        İstanbul Beykoz {mahalle_adi} mahallesi için güncel gayrimenkul piyasası koşullarında:
        Yapı Tipolojisi: {tipoloji}
        
        Aşağıdaki verileri tahmin/araştırma bazlı belirle ve SADECE saf JSON olarak döndür:
        - maliyet_usd (M² inşaat maliyeti USD cinsinden, örn: 1200)
        - satis_usd (M² satış fiyatı USD cinsinden, örn: 4500)

        JSON formatı: {{"maliyet_usd": 1250, "satis_usd": 5200}}
        """
        response = model.generate_content(prompt)
        clean_json = re.search(r'\{.*\}', response.text, re.DOTALL)
        if clean_json:
            return json.loads(clean_json.group())
    except Exception:
        pass
    return None

@st.cache_resource
def setup_tr_fonts():
    urls = [
        "https://github.com/google/fonts/raw/main/ofl/dejavusans/DejaVuSans.ttf",
        "https://cdn.jsdelivr.net/gh/dejavu-fonts/dejavu-fonts-ttf@version_2_37/ttf/DejaVuSans.ttf"
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                pdfmetrics.registerFont(TTFont('TR_Font', io.BytesIO(data)))
                pdfmetrics.registerFont(TTFont('TR_Font_Bold', io.BytesIO(data)))
                return 'TR_Font', 'TR_Font_Bold'
        except Exception:
            continue
    return None, None

FONT_NAME, FONT_BOLD = setup_tr_fonts()

def tr_fix(text):
    if FONT_NAME is not None:
        return str(text)
    mapping = {'İ': 'I', 'I': 'I', 'ı': 'i', 'Ş': 'S', 'ş': 's', 'Ğ': 'G', 'ğ': 'g', 'Ç': 'C', 'ç': 'c', 'Ö': 'O', 'ö': 'o', 'Ü': 'U', 'ü': 'u'}
    text_str = str(text)
    for k, v in mapping.items():
        text_str = text_str.replace(k, v)
    return text_str

USE_FONT = FONT_NAME if FONT_NAME else 'Helvetica'
USE_FONT_BOLD = FONT_BOLD if FONT_BOLD else 'Helvetica-Bold'

try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    gemini_api_key = None

# Session State Tanımları
if "mahalle" not in st.session_state: st.session_state.mahalle = "YAVUZ SELİM"
if "ada" not in st.session_state: st.session_state.ada = "1658"
if "parsel" not in st.session_state: st.session_state.parsel = "1"
if "tapu_alani" not in st.session_state: st.session_state.tapu_alani = 6721.92
if "kaks" not in st.session_state: st.session_state.kaks = 0.45
if "taks" not in st.session_state: st.session_state.taks = 0.30
if "last_uploaded_filename" not in st.session_state: st.session_state.last_uploaded_filename = None
if "last_searched_key" not in st.session_state: st.session_state.last_searched_key = None

# Header Banner
col_header1, col_header2, col_header3 = st.columns([1.5, 4, 1.5])
with col_header1:
    try: st.image("istestate_logo.png", use_container_width=True)
    except Exception: st.caption("istestate_logo.png yüklenemedi")

with col_header2:
    st.markdown("""
    <div style="text-align: center; padding-top: 5px;">
        <h2 style="color: #FFFFFF; font-weight: 800; margin-bottom: 0px; font-size: 26px;">İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK</h2>
        <h3 style="color: #38BDF8; font-weight: 600; margin-top: 0px; font-size: 20px;">& MERİÇ İNŞAAT EMLAK</h3>
        <p style="color: #94A3B8; font-size: 14px; margin-top: 5px;">Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli</p>
    </div>
    """, unsafe_allow_html=True)

with col_header3:
    try: st.image("meric_insaat_emlak_logo.png", use_container_width=True)
    except Exception: st.caption("meric_insaat_emlak_logo.png yüklenemedi")

st.divider()

# SOL PANEL (Girdiler)
with st.sidebar:
    st.markdown("### 📄 1. Belge Analizi & Akıllı Hafıza")
    uploaded_pdf = st.file_uploader("İmar Durumu PDF Raporu Yükleyin", type=["pdf"])

    if not gemini_api_key:
        gemini_api_key = st.text_input("Gemini API Key", type="password")

    # AKILLI HAFIZA & OTOMATİK PDF İŞLEME AKIŞI
    if uploaded_pdf is not None:
        if st.session_state.last_uploaded_filename != uploaded_pdf.name:
            with st.spinner("PDF ve Hafıza Sorgulanıyor..."):
                try:
                    with pdfplumber.open(uploaded_pdf) as pdf:
                        extracted_text = "\n".join([page.extract_text() or "" for page in pdf.pages])

                    if gemini_api_key:
                        genai.configure(api_key=gemini_api_key)
                        model = genai.GenerativeModel('gemini-3.6-flash')
                        
                        prompt = f"""
                        Aşağıdaki imar durumu belgesinden şu bilgileri bul ve SADECE saf JSON formatında döndür:
                        - mahalle (metin)
                        - ada (metin)
                        - parsel (metin)
                        - tapu_alani (sayı)
                        - kaks (sayı)
                        - taks (sayı)

                        PDF Metni:
                        {extracted_text[:4000]}
                        """
                        
                        response = model.generate_content(prompt)
                        clean_json = re.search(r'\{.*\}', response.text, re.DOTALL)
                        
                        if clean_json:
                            data = json.loads(clean_json.group())
                            st.session_state.mahalle = str(data.get("mahalle", st.session_state.mahalle)).upper()
                            st.session_state.ada = str(data.get("ada", st.session_state.ada))
                            st.session_state.parsel = str(data.get("parsel", st.session_state.parsel))
                            st.session_state.tapu_alani = float(data.get("tapu_alani", st.session_state.tapu_alani))
                            st.session_state.kaks = float(data.get("kaks", st.session_state.kaks))
                            st.session_state.taks = float(data.get("taks", st.session_state.taks))
                            
                            db_kayit_ekle_veya_guncelle(
                                st.session_state.mahalle, st.session_state.ada, st.session_state.parsel,
                                st.session_state.tapu_alani, st.session_state.kaks, st.session_state.taks
                            )
                            st.session_state.last_uploaded_filename = uploaded_pdf.name
                            st.toast("PDF Okundu ve Hafızaya Kaydedildi!", icon="⚡")
                            st.rerun()

                except Exception as e:
                    if "429" in str(e):
                        st.warning("⚠️ API Kotası Doldu! Hafızadaki verileri kullanabilirsiniz.")
                    else:
                        st.error(f"PDF Okuma Hatası: {e}")

    st.markdown("---")
    st.markdown("### 📍 2. Parsel & Bölge İmarı")
    
    tum_mahalleler = sorted(list(set(MAHALLE_LISTESI + db_mahalleleri_getir())))
    current_mahalle = str(st.session_state.mahalle).upper()
    
    # Yazım uyuşmazlıkları için esnek indeks eşleştirme
    default_index = 0
    for idx, m in enumerate(tum_mahalleler):
        if m.replace(" ", "") == current_mahalle.replace(" ", ""):
            default_index = idx
            break

    mahalle = st.selectbox("Mahalle Seçin", options=tum_mahalleler, index=default_index)
    st.session_state.mahalle = mahalle

    col_a, col_p = st.columns(2)
    with col_a: ada = st.text_input("Ada No", value=st.session_state.ada)
    with col_p: parsel = st.text_input("Parsel No", value=st.session_state.parsel)

    if st.button("🔍 Hafızadan Bilgi Çek", use_container_width=True):
        hafiza_veri = db_kayit_sorgula(mahalle, ada, parsel)
        if hafiza_veri:
            st.session_state.tapu_alani = hafiza_veri[0]
            st.session_state.kaks = hafiza_veri[1]
            st.session_state.taks = hafiza_veri[2]
            st.session_state.ada = ada
            st.session_state.parsel = parsel
            st.success("✅ Veriler hafızadan çekildi!")
            st.rerun()
        else:
            st.error(f"❌ {mahalle} {ada}/{parsel} için kaydedilmiş bir veri bulunamadı.")

    imar_fonksiyonu = st.selectbox("İmar Fonksiyon Alanı", ["KONUT ALANI", "TİCARET VE KONUT ALANI", "TİCARET ALANI"])
    yapi_tipolojisi = st.selectbox("Mimari Yapı Tipolojisi Tercihi", ["Müstakil Villa", "İkiz Villa", "Bahçe - Çatı Dubleksi", "Standart Daire / Konut"])

    st.markdown("#### 🏊 Havuz Proje Seçenekleri")
    havuz_tercihi = st.selectbox("Havuz Tipi", ["Havuzsuz", "Müstakil Havuzlu (Her Üniteye)", "Ortak Kullanım Havuzlu"])
    
    havuz_m2_birim = 0.0
    if havuz_tercihi == "Müstakil Havuzlu (Her Üniteye)":
        havuz_m2_birim = st.number_input("Ünite Başı Müstakil Havuz Alanı (m²)", value=35.0, step=5.0)
    elif havuz_tercihi == "Ortak Kullanım Havuzlu":
        havuz_m2_birim = st.number_input("Toplam Ortak Havuz Alanı (m²)", value=120.0, step=10.0)

    tapu_alani = st.number_input("Tapu Alanı (m²)", value=float(st.session_state.tapu_alani), step=10.0)
    nitelik = st.selectbox("Nitelik", ["Bahçe", "Arsa", "Tarla"])
    terk_durumu = st.checkbox("18. Madde Terki Yapıldı mı?", value=False)
    
    col_k, col_t = st.columns(2)
    with col_k: kaks = st.number_input("KAKS (Emsal)", value=float(st.session_state.kaks), step=0.05)
    with col_t: taks = st.number_input("TAKS", value=float(st.session_state.taks), step=0.05)
    
    if st.button("💾 Mevcut Verileri Hafızaya Kaydet/Güncelle", use_container_width=True):
        db_kayit_ekle_veya_guncelle(mahalle, ada, parsel, tapu_alani, kaks, taks)
        st.toast("Veriler başarıyla hafızaya kaydedildi!", icon="✅")

    sunum_tipi = st.selectbox("Sunum Modeli", ["Satılık", "Kat Karşılığı"])

    st.markdown("---")
    st.markdown("### 💰 3. Finansal Parametreler ($ USD)")

    current_search_key = f"{mahalle}_{yapi_tipolojisi}"
    if st.session_state.last_searched_key != current_search_key:
        usd_rate = get_tcmb_usd_rate()
        market_data = fetch_market_prices_via_gemini(mahalle, yapi_tipolojisi, gemini_api_key) if gemini_api_key else None
        
        if market_data and "maliyet_usd" in market_data and "satis_usd" in market_data:
            st.session_state.auto_maliyet_usd = int(market_data["maliyet_usd"])
            st.session_state.auto_satis_usd = int(market_data["satis_usd"])
        else:
            maliyet_tl = 48000 if yapi_tipolojisi in ["Müstakil Villa", "İkiz Villa"] else 38000
            satis_tl = 185000 if yapi_tipolojisi in ["Müstakil Villa", "İkiz Villa"] else 140000
            st.session_state.auto_maliyet_usd = int(maliyet_tl / usd_rate)
            st.session_state.auto_satis_usd = int(satis_tl / usd_rate)
            
        st.session_state.last_searched_key = current_search_key

    birim_maliyeti_usd = st.number_input("M² İnşaat Maliyeti ($)", value=st.session_state.get("auto_maliyet_usd", 1200), step=50)
    satis_m2_fiyati_usd = st.number_input("M² Satış Fiyatı ($)", value=st.session_state.get("auto_satis_usd", 5000), step=100)
    kat_karsiligi_orani = st.slider("Kat Karşılığı Payı (%)", 30, 60, 50) if sunum_tipi == "Kat Karşılığı" else 50
    unite_m2 = st.number_input("Ortalama Ünite Brüt m²", value=200, step=10)

# TEMEL İMAR HESAPLARI
if terk_durumu or nitelik.lower() == 'arsa':
    net_alan = tapu_alani
    kesinti_orani = 0.0
    terk_str = "18. Madde Terki Yapılmış"
else:
    net_alan = tapu_alani * 0.70
    kesinti_orani = 0.30
    terk_str = "18. Madde Terksiz (%30 DOP)"

net_emsal_alani = net_alan * kaks
ilave_emsal_harici = net_emsal_alani * 0.30
ham_toplam_brut_insaat = net_emsal_alani * 1.30
max_taban_alani = net_alan * taks

gecici_unite_adedi = int(ham_toplam_brut_insaat / unite_m2) if unite_m2 > 0 else 0

if havuz_tercihi == "Müstakil Havuzlu (Her Üniteye)":
    toplam_havuz_alani = gecici_unite_adedi * havuz_m2_birim
elif havuz_tercihi == "Ortak Kullanım Havuzlu":
    toplam_havuz_alani = havuz_m2_birim
else:
    toplam_havuz_alani = 0.0

toplam_brut_insaat = max(0.0, ham_toplam_brut_insaat - toplam_havuz_alani)
toplam_unite_adedi = int(toplam_brut_insaat / unite_m2) if unite_m2 > 0 else 0

toplam_insaat_maliyeti_usd = ham_toplam_brut_insaat * birim_maliyeti_usd
toplam_proje_geliri_usd = toplam_brut_insaat * satis_m2_fiyati_usd

if sunum_tipi == "Kat Karşılığı":
    mutaahhit_payi_m2 = toplam_brut_insaat * (100 - kat_karsiligi_orani) / 100
    arsa_sahibi_payi_m2 = toplam_brut_insaat * kat_karsiligi_orani / 100
    mutaahhit_unite_adedi = int(mutaahhit_payi_m2 / unite_m2) if unite_m2 > 0 else 0
    arsa_sahibi_unite_adedi = int(arsa_sahibi_payi_m2 / unite_m2) if unite_m2 > 0 else 0
    mutaahhit_net_kar_usd = (mutaahhit_payi_m2 * satis_m2_fiyati_usd) - toplam_insaat_maliyeti_usd
else:
    mutaahhit_net_kar_usd = toplam_proje_geliri_usd - toplam_insaat_maliyeti_usd

# ANA SEKMELER
tab1, tab2, tab3, tab4 = st.tabs(["📐 İmar & Kapasite Analizi", "🏗️ Mimari Potansiyel & Havuz Detayı", "💰 Finansal Fizibilite ($ USD)", "🗄️ Sistem Hafızası"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Brüt Arazi Alanı", f"{tapu_alani:,.2f} m²")
    c2.metric("Hesaba Esas Net Alan", f"{net_alan:,.2f} m²", delta=f"-%{int(kesinti_orani*100)} DOP" if kesinti_orani > 0 else "Kesintisiz")
    c3.metric("Net Emsal Alanı", f"{net_emsal_alani:,.2f} m²")
    c4.metric("NET KAPALI İNŞAAT", f"{toplam_brut_insaat:,.2f} m²", delta=f"-{toplam_havuz_alani:,.1f} m² Havuz Payı" if toplam_havuz_alani > 0 else "Havuzsuz")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📋 İmar Parametre Detayları")
    df_imar = pd.DataFrame({
        "Parametre": ["İmar Fonksiyonu", "Yapı Tipolojisi", "Havuz Durumu", "Terk/DOP Durumu", "Uygulanan KAKS (Emsal)", "TAKS (Taban Alanı Katsayısı)", "Max Taban Alanı", "%30 İlave Emsal Harici"],
        "Değer": [imar_fonksiyonu, yapi_tipolojisi, f"{havuz_tercihi} ({toplam_havuz_alani:,.1f} m²)", terk_str, f"{kaks:.2f}", f"{taks:.2f}", f"{max_taban_alani:,.2f} m²", f"{ilave_emsal_harici:,.2f} m²"]
    })
    st.table(df_imar)

with tab2:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown(f"#### 🏛️ Bölgesel Mimari Planlama ({imar_fonksiyonu})")
        st.info(f"""
        * **Tercih Edilen Tipoloji:** {yapi_tipolojisi}
        * **Havuz Konfigürasyonu:** {havuz_tercihi}
        * **Toplam Havuz M² Alanı:** {toplam_havuz_alani:,.2f} m²
        * **Ortalama Konut Ünite Büyüklüğü:** {unite_m2} m²
        * **Tahmini Bağımsız Bölüm Sayısı:** ~{toplam_unite_adedi} Adet Konut
        * **Taban Oturumu (TAKS Sınırı):** ~{max_taban_alani:,.2f} m²
        """)
    with col_m2:
        if sunum_tipi == "Kat Karşılığı":
            st.markdown(f"#### 🤝 Kat Karşılığı Paylaşım Modeli (%{kat_karsiligi_orani} Arsa / %{100-kat_karsiligi_orani} Müteahhit)")
            st.success(f"""
            * **Arsa Sahibi Kalan Net İnşaat:** {arsa_sahibi_payi_m2:,.2f} m² (~{arsa_sahibi_unite_adedi} Ünite)
            * **Müteahhit Kalan Net İnşaat:** {mutaahhit_payi_m2:,.2f} m² (~{mutaahhit_unite_adedi} Ünite)
            """)

with tab3:
    f1, f2, f3 = st.columns(3)
    f1.metric("Toplam İnşaat Maliyeti", f"${toplam_insaat_maliyeti_usd:,.0f}")
    f2.metric("Toplam Proje Ciro Hacmi", f"${toplam_proje_geliri_usd:,.0f}")
    f3.metric("Tahmini Net Kar / Proje Marjı", f"${mutaahhit_net_kar_usd:,.0f}")

with tab4:
    st.markdown("#### 🗄️ Veri Tabanında Kayıtlı Tüm Parseller")
    conn = sqlite3.connect("imar_hafizasi.db")
    df_db = pd.read_sql_query("SELECT mahalle AS Mahalle, ada AS Ada, parsel AS Parsel, tapu_alani AS 'Tapu Alanı', kaks AS KAKS, taks AS TAKS FROM imar_kayitlari", conn)
    conn.close()
    if not df_db.empty:
        st.dataframe(df_db, use_container_width=True)
    else:
        st.info("Sistem hafızasında henüz kayıtlı veri bulunmuyor.")

# PDF Oluşturma
def yatay_kurumsal_pdf_olustur():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4), 
        rightMargin=20, leftMargin=20, topMargin=20, bottomMargin=20
    )
    story = []

    banner_title = ParagraphStyle('BTitle', fontName=USE_FONT_BOLD, fontSize=11, textColor=colors.white, alignment=1, leading=14)
    th_style = ParagraphStyle('TH', fontName=USE_FONT_BOLD, fontSize=7.5, textColor=colors.white, alignment=1, leading=9)
    td_style = ParagraphStyle('TD', fontName=USE_FONT, fontSize=8, textColor=colors.HexColor('#1E293B'), alignment=1, leading=10)
    td_bold = ParagraphStyle('TDBold', fontName=USE_FONT_BOLD, fontSize=8, textColor=colors.HexColor('#0F172A'), alignment=1, leading=10)
    section_title = ParagraphStyle('SecTitle', fontName=USE_FONT_BOLD, fontSize=9, textColor=colors.HexColor('#1B2A47'), spaceAfter=4)
    footer_style = ParagraphStyle('Footer', fontName=USE_FONT, fontSize=7.5, textColor=colors.HexColor('#475569'), leading=11)

    try:
        img_ist = RLImage("istestate_logo.png", width=140, height=42)
        img_mer = RLImage("meric_insaat_emlak_logo.png", width=150, height=42)
        
        box_ist = Table([[img_ist]], colWidths=[146])
        box_ist.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.white), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3)]))

        box_mer = Table([[img_mer]], colWidths=[156])
        box_mer.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,-1), colors.white), ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 3), ('BOTTOMPADDING', (0,0), (-1,-1), 3)]))

        banner_text = Paragraph(
            f"<b>{tr_fix('İSTESTATE & MERİÇ İNŞAAT EMLAK')}</b><br/>"
            f"<font size=8 color='#E2E8F0'>{tr_fix('DETAYLI İMAR, MİMARİ POTANSİYEL VE FİNANSAL FİZİBİLİTE RAPORU')}</font>", 
            banner_title
        )
        
        banner_table = Table([[box_ist, banner_text, box_mer]], colWidths=[156, 490, 156])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1B2A47')),
            ('ALIGN', (0,0), (0,0), 'LEFT'), ('ALIGN', (1,0), (1,0), 'CENTER'), ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 5), ('BOTTOMPADDING', (0,0), (-1,-1), 5)
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 10))
    except Exception:
        pass

    # TABLO 1: İMAR VE KAPASİTE
    story.append(Paragraph(tr_fix("1. PARSEL BAZLI İMAR VE KAPASİTE TABLOSU"), section_title))
    headers_t1 = [
        Paragraph(tr_fix("MAHALLE"), th_style), Paragraph(tr_fix("ADA"), th_style), Paragraph(tr_fix("PARSEL"), th_style),
        Paragraph(tr_fix("NİTELİK"), th_style), Paragraph(tr_fix("PARSEL ALANI (M²)"), th_style), Paragraph(tr_fix("NET ALAN (M²)"), th_style),
        Paragraph(tr_fix("FONKSİYON"), th_style), Paragraph(tr_fix("KAKS"), th_style), Paragraph(tr_fix("HAM İNŞAAT (M²)"), th_style), Paragraph(tr_fix("NET KAPALI İNŞAAT (M²)"), th_style)
    ]
    row_t1 = [
        Paragraph(tr_fix(mahalle), td_style), Paragraph(tr_fix(str(ada)), td_style), Paragraph(tr_fix(str(parsel)), td_style),
        Paragraph(tr_fix(nitelik), td_style), Paragraph(f"{tapu_alani:,.2f}", td_style), Paragraph(f"{net_alan:,.2f}", td_style),
        Paragraph(tr_fix(imar_fonksiyonu), td_style), Paragraph(f"{kaks:.2f}", td_style), Paragraph(f"{ham_toplam_brut_insaat:,.2f}", td_style), Paragraph(f"{toplam_brut_insaat:,.2f}", td_bold)
    ]
    table1 = Table([headers_t1, row_t1], colWidths=[80, 45, 45, 70, 95, 90, 125, 45, 100, 107])
    table1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1B2A47')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F8FAFC'))
    ]))
    story.append(table1)
    story.append(Spacer(1, 10))

    # TABLO 2: MİMARİ POTANSİYEL VE HAVUZ DETAYI
    story.append(Paragraph(tr_fix("2. MİMARİ POTANSİYEL VE HAVUZ YAPILAŞMA DETAYI"), section_title))
    headers_t2 = [
        Paragraph(tr_fix("YAPI TİPOLOJİSİ"), th_style), Paragraph(tr_fix("HAVUZ TİPİ VE ALANI"), th_style), Paragraph(tr_fix("ORTALAMA ÜNİTE BRÜT M²"), th_style), Paragraph(tr_fix("TAHMİNİ ÜNİTE ADEDİ"), th_style),
        Paragraph(tr_fix("TAKS (TABAN KATSAYISI)"), th_style), Paragraph(tr_fix("MAX TABAN OTURUMU (M²)"), th_style)
    ]
    row_t2 = [
        Paragraph(tr_fix(yapi_tipolojisi), td_style), Paragraph(tr_fix(f"{havuz_tercihi} ({toplam_havuz_alani:,.1f} m²)"), td_style), Paragraph(f"{unite_m2} m²", td_style), Paragraph(f"~{toplam_unite_adedi} Adet", td_bold),
        Paragraph(f"{taks:.2f}", td_style), Paragraph(f"{max_taban_alani:,.2f} m²", td_style)
    ]
    table2 = Table([headers_t2, row_t2], colWidths=[150, 150, 110, 110, 140, 142])
    table2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2A3B5C')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F8FAFC'))
    ]))
    story.append(table2)
    story.append(Spacer(1, 10))

    # TABLO 3: FİNANSAL FİZİBİLİTE
    story.append(Paragraph(tr_fix("3. FİNANSAL FİZİBİLİTE ANALİZİ ($ USD)"), section_title))
    headers_t3 = [
        Paragraph(tr_fix("M² İNŞAAT MALİYETİ ($)"), th_style), Paragraph(tr_fix("TOPLAM İNŞAAT MALİYETİ ($)"), th_style),
        Paragraph(tr_fix("M² SATIŞ FİYATI ($)"), th_style), Paragraph(tr_fix("TOPLAM PROJE CİROSU ($)"), th_style), Paragraph(tr_fix("TAHMİNİ NET KAR MARJI ($)"), th_style)
    ]
    row_t3 = [
        Paragraph(f"${birim_maliyeti_usd:,.0f}", td_style), Paragraph(f"${toplam_insaat_maliyeti_usd:,.0f}", td_style),
        Paragraph(f"${satis_m2_fiyati_usd:,.0f}", td_style), Paragraph(f"${toplam_proje_geliri_usd:,.0f}", td_style), Paragraph(f"${mutaahhit_net_kar_usd:,.0f}", td_bold)
    ]
    table3 = Table([headers_t3, row_t3], colWidths=[150, 160, 150, 170, 172])
    table3.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1E3A8A')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F8FAFC'))
    ]))
    story.append(table3)
    story.append(Spacer(1, 10))

    # TABLO 4: KAT KARŞILIĞI (Opsiyonel)
    if sunum_tipi == "Kat Karşılığı":
        story.append(Paragraph(tr_fix(f"4. KAT KARŞILIĞI PAYLAŞIM DETAYLARI (%{kat_karsiligi_orani} ARSA / %{100-kat_karsiligi_orani} MÜTEAHHİT)"), section_title))
        headers_t4 = [
            Paragraph(tr_fix("PAYDAŞ"), th_style), Paragraph(tr_fix("PAY ORANI (%)"), th_style),
            Paragraph(tr_fix("KALAN NET İNŞAAT ALANI (M²)"), th_style), Paragraph(tr_fix("TAHMİNİ BAĞIMSIZ BÖLÜM ADEDİ"), th_style)
        ]
        row_t4_1 = [Paragraph(tr_fix("Arsa Sahibi Payı"), td_style), Paragraph(f"%{kat_karsiligi_orani}", td_style), Paragraph(f"{arsa_sahibi_payi_m2:,.2f} m²", td_style), Paragraph(f"~{arsa_sahibi_unite_adedi} Adet", td_bold)]
        row_t4_2 = [Paragraph(tr_fix("Müteahhit Payı"), td_style), Paragraph(f"%{100-kat_karsiligi_orani}", td_style), Paragraph(f"{mutaahhit_payi_m2:,.2f} m²", td_style), Paragraph(f"~{mutaahhit_unite_adedi} Adet", td_bold)]
        table4 = Table([headers_t4, row_t4_1, row_t4_2], colWidths=[180, 150, 230, 242])
        table4.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#334155')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'), ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F8FAFC'))
        ]))
        story.append(table4)
        story.append(Spacer(1, 10))

    iletisim = tr_fix("<b>İstestate Meriç Gayrimenkul Danışmanlık & Meriç İnşaat Emlak</b> | ") + \
               tr_fix(f"Umutcan K. MERİÇ (0539 451 61 61) - Süleyman MERİÇ (0532 695 10 83)<br/>") + \
               tr_fix(f"<b>Adres:</b> Çiftlik Mah. Çavuşbaşı Cumhuriyet Cad. No:171/3 Beykoz/İSTANBUL")
    story.append(Paragraph(iletisim, footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

clean_mahalle = re.sub(r'[^\w\s-]', '', mahalle).strip().replace(" ", "_")
kurumsal_dosya_adi = f"ISTESTATE_MERIC_Fizibilite_Raporu_{clean_mahalle}_{ada}_{parsel}_2026.pdf"

st.divider()
st.download_button(
    label="📄 Kurumsal PDF Raporunu İndir ($ USD)",
    data=yatay_kurumsal_pdf_olustur(),
    file_name=kurumsal_dosya_adi,
    mime="application/pdf"
)
