import io
import json
import re
import sqlite3
import time
import urllib.request
import xml.etree.ElementTree as ET
import google.generativeai as genai
import pandas as pd
import pdfplumber
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Sayfa Yapılandırması
st.set_page_config(
    page_title="İstestate Meriç - İmar & Fizibilite Portalı",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# BÖLGE VE MAHALLE HİYERARŞİSİ
# ---------------------------------------------------------
BOLGE_MAHALLE_HARITASI = {
    "Anadoluhisarı": ["Anadolu Hisarı", "Kanlıca", "Kavacık"],
    "Beykoz": [
        "Gümüşsuyu",
        "Merkez",
        "Ortaçeşme",
        "Tokatköy",
        "Yalıköy",
        "Yeni Mahalle",
    ],
    "Çavuşbaşı": ["Baklacı", "Çiftlik", "Çengeldere", "Fatih", "Yavuz Selim"],
    "Çubuklu": ["Çubuklu", "Rüzgarlıbahçe"],
    "Göksu": ["Göksu", "Göztepe"],
    "Paşabahçe": ["Acarlar", "Çiğdem", "İncirköy", "Paşabahçe", "Soğuksu"],
    "Tokatköy": ["Anadolu Kavağı", "Çamlıbahçe", "Tokatköy", "Yalıköy"],
    "Köyler": [
        "Akbaba",
        "Alibahadır",
        "Anadolufeneri",
        "Bozhane",
        "Cumhuriyetköy",
        "Dereseki",
        "Elmalı",
        "Göllü",
        "Görele",
        "İshaklı",
        "Kaynarca",
        "Kılıçlı",
        "Mahmutşevketpaşa",
        "Öğümce",
        "Örnekköy",
        "Paşamandıra",
        "Polonezköy",
        "Poyrazköy",
        "Riva",
        "Zerzavatçı",
    ],
}

IMAR_FONKSIYONLARI = [
    "KONUT ALANI",
    "TİCARET VE KONUT ALANI",
    "TİCARET ALANI",
    "TURİZM ALANI",
    "SANAYİ ALANI",
]


def clean_mahalle_name(name):
    if not name:
        return ""
    name = str(name).strip()
    pattern = r"(?i)\b(ÇAVUŞBAŞI\s+)?(mh\.?|mah\.?|mahallesi)\b"
    cleaned = re.sub(pattern, "", name).strip()
    cleaned = cleaned.replace("YAVUZSELİM", "YAVUZ SELİM").replace(
        "Yavuzselim", "Yavuz Selim"
    )

    for key, value in BOLGE_MAHALLE_HARITASI.items():
        for item in value:
            if item.lower() in cleaned.lower() or cleaned.lower() in item.lower():
                return item

    return cleaned if cleaned else name.strip()


# LOCAL REGEX PARSER (GÜNCELLENDİ)
def fallback_regex_parser(extracted_text):
    data = {}

    mahalle_match = re.search(
        r"Mahalle\s*[\n\r:]*\s*([A-ZÇĞİÖŞÜa-zçğıöşü\s]+?)(?=\s*Pafta|\s*\n|\s*\||$)",
        extracted_text,
        re.IGNORECASE,
    )
    if mahalle_match:
        data["mahalle"] = mahalle_match.group(1).strip()

    ada_match = re.search(r"Ada\s*[\n\r]*\s*\|\s*(\d+)", extracted_text, re.IGNORECASE) or re.search(r"Ada\s*:\s*(\d+)", extracted_text, re.IGNORECASE)
    if ada_match:
        data["ada"] = ada_match.group(1).strip()

    parsel_match = re.search(r"Parsel\s*[\n\r]*\s*\|\s*(\d+)", extracted_text, re.IGNORECASE) or re.search(r"Parsel\s*:\s*(\d+)", extracted_text, re.IGNORECASE)
    if parsel_match:
        data["parsel"] = parsel_match.group(1).strip()

    alan_match = re.search(r"Alan\s*\*?\s*[\n\r]*\s*\|\s*([\d\.,]+)", extracted_text, re.IGNORECASE) or re.search(r"Alan\s*\*?\s*\n\s*([\d\.,]+)\s*m²", extracted_text, re.IGNORECASE)
    if alan_match:
        val = alan_match.group(1).replace(".", "").replace(",", ".")
        try:
            data["tapu_alani"] = float(val)
        except Exception:
            pass

    kaks_match = re.search(r"Kaks\s*\([^\)]*\)\s*[\n\r]*\s*\|\s*([\d\.,]+)", extracted_text, re.IGNORECASE) or re.search(r"Kaks\s*\(Emsal\)\s*\n\s*([\d\.,]+)", extracted_text, re.IGNORECASE)
    if kaks_match:
        val = kaks_match.group(1).replace(",", ".")
        try:
            data["kaks"] = float(val)
        except Exception:
            pass

    taks_match = re.search(r"Taks\s*[\n\r]*\s*\|\s*([\d\.,]+)", extracted_text, re.IGNORECASE) or re.search(r"Taks\s*\n\s*([\d\.,]+)", extracted_text, re.IGNORECASE)
    if taks_match:
        val = taks_match.group(1).replace(",", ".")
        try:
            data["taks"] = float(val)
        except Exception:
            pass

    fonks_match = re.search(r"Fonksiyon Adı\s*[\n\r]*\s*\|\s*([^\n\r\|]+)", extracted_text, re.IGNORECASE)
    if fonks_match:
        data["imar_fonksiyonu"] = fonks_match.group(1).strip()

    konut_match = re.search(
        r"KONUT ALANI[\s\S]*?Fonksiyon Alanına\s*Giren[\s\S]*?(?:%\s*([\d\.,]+))?[\s\S]*?([\d\.,]+)\s*m²",
        extracted_text,
        re.IGNORECASE,
    )
    if konut_match:
        val_konut = konut_match.group(2).replace(".", "").replace(",", ".")
        try:
            data["net_konut_alani"] = float(val_konut)
        except Exception:
            pass
        if konut_match.group(1):
            try:
                data["net_konut_orani"] = float(konut_match.group(1).replace(",", "."))
            except Exception:
                pass

    park_match = re.search(
        r"PARK[\s\S]*?Fonksiyon Alanına\s*Giren[\s\S]*?(?:%\s*([\d\.,]+))?[\s\S]*?([\d\.,]+)\s*m²",
        extracted_text,
        re.IGNORECASE,
    )
    if park_match:
        val_park = park_match.group(2).replace(".", "").replace(",", ".")
        try:
            data["park_terk_alani"] = float(val_park)
        except Exception:
            pass

    return data


def parse_pdf_with_gemini_retry(pdf_text, api_key, max_retries=3):
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-3.6-flash")

    prompt = f"""
    Aşağıdaki imar durumu belgesinden şu bilgileri bul ve SADECE saf JSON formatında döndür:
    - mahalle (metin, 'Mahalle' etiketli alandaki tam mahalle adını al)
    - ada (metin)
    - parsel (metin)
    - tapu_alani (sayı, Toplam / Brüt parsel alanı)
    - net_konut_alani (sayı, 'KONUT ALANI' karşısındaki m² değeri)
    - net_konut_orani (sayı, Konut alanının yüzde oranı)
    - park_terk_alani (sayı, varsa PARK / Terk m² değeri, yoksa 0)
    - kaks (sayı, Emsal)
    - taks (sayı)
    - imar_fonksiyonu (Örn: KONUT ALANI, TİCARET VE KONUT ALANI vb.)

    PDF Metni:
    {pdf_text[:4000]}
    """

    for attempt in range(max_retries):
        try:
            response = model.generate_content(prompt)
            clean_json = re.search(r"\{.*\}", response.text, re.DOTALL)
            if clean_json:
                return json.loads(clean_json.group())
        except Exception as e:
            err_msg = str(e)
            if "429" in err_msg or "quota" in err_msg.lower():
                time.sleep(12)
            else:
                break
    return None


def init_db():
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS imar_kayitlari (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mahalle TEXT,
                ada TEXT,
                parsel TEXT,
                tapu_alani REAL,
                net_konut_alani REAL,
                net_konut_orani REAL,
                park_terk_alani REAL,
                terk_yapilmis INTEGER DEFAULT 0,
                kaks REAL,
                taks REAL,
                imar_fonksiyonu TEXT,
                UNIQUE(mahalle, ada, parsel)
            )
        """
        )
        cursor.execute("PRAGMA table_info(imar_kayitlari)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if "imar_fonksiyonu" not in columns:
            cursor.execute("ALTER TABLE imar_kayitlari ADD COLUMN imar_fonksiyonu TEXT")
        if "net_konut_alani" not in columns:
            cursor.execute("ALTER TABLE imar_kayitlari ADD COLUMN net_konut_alani REAL DEFAULT 0.0")
        if "net_konut_orani" not in columns:
            cursor.execute("ALTER TABLE imar_kayitlari ADD COLUMN net_konut_orani REAL DEFAULT 0.0")
        if "park_terk_alani" not in columns:
            cursor.execute("ALTER TABLE imar_kayitlari ADD COLUMN park_terk_alani REAL DEFAULT 0.0")
        if "terk_yapilmis" not in columns:
            cursor.execute("ALTER TABLE imar_kayitlari ADD COLUMN terk_yapilmis INTEGER DEFAULT 0")

        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Veritabanı başlatılırken hata oluştu: {e}")


init_db()


def db_kayit_ekle_veya_guncelle(
    mahalle, ada, parsel, tapu_alani, net_konut_alani, net_konut_orani, park_terk_alani, terk_yapilmis, kaks, taks, imar_fonksiyonu
):
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        cursor = conn.cursor()
        sade_mahalle = clean_mahalle_name(mahalle).upper()
        cursor.execute(
            """
            INSERT INTO imar_kayitlari (mahalle, ada, parsel, tapu_alani, net_konut_alani, net_konut_orani, park_terk_alani, terk_yapilmis, kaks, taks, imar_fonksiyonu)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(mahalle, ada, parsel) DO UPDATE SET
                tapu_alani=excluded.tapu_alani,
                net_konut_alani=excluded.net_konut_alani,
                net_konut_orani=excluded.net_konut_orani,
                park_terk_alani=excluded.park_terk_alani,
                terk_yapilmis=excluded.terk_yapilmis,
                kaks=excluded.kaks,
                taks=excluded.taks,
                imar_fonksiyonu=excluded.imar_fonksiyonu
        """,
            (
                sade_mahalle,
                str(ada).strip(),
                str(parsel).strip(),
                float(tapu_alani or 0.0),
                float(net_konut_alani or 0.0),
                float(net_konut_orani or 0.0),
                float(park_terk_alani or 0.0),
                int(1 if terk_yapilmis else 0),
                float(kaks or 0.0),
                float(taks or 0.0),
                str(imar_fonksiyonu),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Kayıt ekleme/güncelleme hatası: {e}")


def db_kayit_sil(record_id):
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM imar_kayitlari WHERE id = ?", (record_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Kayıt silme hatası: {e}")


def db_kayit_sorgula(ada, parsel):
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        cursor = conn.cursor()

        ada_str = str(ada).strip()
        parsel_str = str(parsel).strip()

        cursor.execute(
            """
            SELECT mahalle, tapu_alani, net_konut_alani, net_konut_orani, park_terk_alani, terk_yapilmis, kaks, taks, imar_fonksiyonu 
            FROM imar_kayitlari 
            WHERE CAST(ada AS TEXT) = ? 
              AND CAST(parsel AS TEXT) = ?
        """,
            (ada_str, parsel_str),
        )

        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        st.error(f"Veritabanı Okuma Hatası: {e}")
        return None


def get_birlesik_parsel_verisi(record_ids):
    if not record_ids:
        return None

    conn = sqlite3.connect("imar_hafizasi.db")
    placeholders = ",".join(["?"] * len(record_ids))
    query = f"SELECT * FROM imar_kayitlari WHERE id IN ({placeholders})"
    df = pd.read_sql_query(query, conn, params=record_ids)
    conn.close()

    if df.empty:
        return None

    toplam_tapu = df["tapu_alani"].sum()
    toplam_net_konut = df["net_konut_alani"].sum()
    toplam_park = df["park_terk_alani"].sum()
    net_oranh_ort = round((toplam_net_konut / toplam_tapu) * 100, 2) if toplam_tapu > 0 else 0

    agirlikli_kaks = (
        (df["tapu_alani"] * df["kaks"]).sum() / toplam_tapu
        if toplam_tapu > 0
        else 0
    )
    agirlikli_taks = (
        (df["tapu_alani"] * df["taks"]).sum() / toplam_tapu
        if toplam_tapu > 0
        else 0
    )

    return {
        "ada": ", ".join(df["ada"].astype(str).unique()),
        "parsel": ", ".join(df["parsel"].astype(str).unique()),
        "mahalle": df["mahalle"].iloc[0] if not df.empty else "",
        "toplam_tapu": toplam_tapu,
        "net_konut_alani": toplam_net_konut,
        "net_konut_orani": net_oranh_ort,
        "park_terk_alani": toplam_park,
        "terk_yapilmis": df["terk_yapilmis"].iloc[0] if "terk_yapilmis" in df else 0,
        "kaks": agirlikli_kaks,
        "taks": agirlikli_taks,
        "imar_fonksiyonu": (
            df["imar_fonksiyonu"].iloc[0] if "imar_fonksiyonu" in df else ""
        ),
        "detay_df": df,
    }


# STİL VE YARDIMCI METOTLAR
st.markdown(
    """
<style>
    .main { background-color: #0F172A; }
    section[data-testid="stSidebar"] { background-color: #1E293B !important; border-right: 1px solid #334155; }
    div[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 700 !important; color: #38BDF8 !important; }
    div[data-testid="stMetric"] { background-color: #1E293B; border: 1px solid #334155; border-radius: 10px; padding: 15px; }
    .stTabs [data-baseweb="tab"] { background-color: #1E293B; border-radius: 8px 8px 0px 0px; padding: 10px 20px; color: #94A3B8; border: 1px solid #334155; }
    .stTabs [aria-selected="true"] { background-color: #2563EB !important; color: #FFFFFF !important; border-color: #2563EB !important; }
    .stDownloadButton > button { width: 100%; background-color: #059669 !important; color: white !important; font-weight: 600 !important; border-radius: 8px !important; padding: 12px 24px !important; border: none !important; }
</style>
""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600)
def get_tcmb_usd_rate():
    try:
        url = "https://www.tcmb.gov.tr/kurlar/today.xml"
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            tree = ET.parse(response)
            root = tree.getroot()
            for currency in root.findall("Currency"):
                if currency.get("CurrencyCode") == "USD":
                    return float(currency.find("ForexBuying").text)
    except Exception:
        return 34.50


@st.cache_data(ttl=1800)
def fetch_market_prices_via_gemini(mahalle_adi, tipoloji, api_key):
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-3.6-flash")
        prompt = f"""
        İstanbul Beykoz {mahalle_adi} mahallesi için güncel gayrimenkul piyasası koşullarında:
        Yapı Tipolojisi: {tipoloji}
        Aşağıdaki verileri tahmin/araştırma bazlı belirle ve SADECE saf JSON olarak döndür:
        - maliyet_usd (M² inşaat maliyeti USD cinsinden, örn: 1200)
        - satis_usd (M² satış fiyatı USD cinsinden, örn: 4500)
        JSON formatı: {{"maliyet_usd": 1250, "satis_usd": 5200}}
        """
        response = model.generate_content(prompt)
        clean_json = re.search(r"\{.*\}", response.text, re.DOTALL)
        if clean_json:
            return json.loads(clean_json.group())
    except Exception:
        pass
    return None


@st.cache_resource
def setup_tr_fonts():
    urls = [
        "https://github.com/google/fonts/raw/main/ofl/dejavusans/DejaVuSans.ttf",
        "https://cdn.jsdelivr.net/gh/dejavu-fonts/dejavu-fonts-ttf@version_2_37/ttf/DejaVuSans.ttf",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = resp.read()
                pdfmetrics.registerFont(TTFont("TR_Font", io.BytesIO(data)))
                pdfmetrics.registerFont(
                    TTFont("TR_Font_Bold", io.BytesIO(data))
                )
                return "TR_Font", "TR_Font_Bold"
        except Exception:
            continue
    return None, None


FONT_NAME, FONT_BOLD = setup_tr_fonts()


def tr_fix(text):
    if FONT_NAME is not None:
        return str(text)
    mapping = {
        "İ": "I",
        "I": "I",
        "ı": "i",
        "Ş": "S",
        "ş": "s",
        "Ğ": "G",
        "ğ": "g",
        "Ç": "C",
        "ç": "c",
        "Ö": "O",
        "ö": "o",
        "Ü": "U",
        "ü": "u",
    }
    text_str = str(text)
    for k, v in mapping.items():
        text_str = text_str.replace(k, v)
    return text_str


USE_FONT = FONT_NAME if FONT_NAME else "Helvetica"
USE_FONT_BOLD = FONT_BOLD if FONT_BOLD else "Helvetica-Bold"

try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    gemini_api_key = None

# Session State Initializations
if "bolge" not in st.session_state:
    st.session_state.bolge = "Çavuşbaşı"
if "mahalle" not in st.session_state:
    st.session_state.mahalle = "Çiftlik"
if "ada" not in st.session_state:
    st.session_state.ada = "1617"
if "parsel" not in st.session_state:
    st.session_state.parsel = "13"
if "tapu_alani" not in st.session_state:
    st.session_state.tapu_alani = 2131.58
if "net_konut_alani" not in st.session_state:
    st.session_state.net_konut_alani = 1593.16
if "net_konut_orani" not in st.session_state:
    st.session_state.net_konut_orani = 74.74
if "park_terk_alani" not in st.session_state:
    st.session_state.park_terk_alani = 369.62
if "terk_yapilmis" not in st.session_state:
    st.session_state.terk_yapilmis = False
if "kaks" not in st.session_state:
    st.session_state.kaks = 0.30
if "taks" not in st.session_state:
    st.session_state.taks = 0.30
if "imar_fonksiyonu" not in st.session_state:
    st.session_state.imar_fonksiyonu = "KONUT ALANI"
if "processed_files" not in st.session_state:
    st.session_state.processed_files = []
if "last_searched_key" not in st.session_state:
    st.session_state.last_searched_key = None

if "tevhid_aktif" not in st.session_state:
    st.session_state.tevhid_aktif = False
if "tevhid_df" not in st.session_state:
    st.session_state.tevhid_df = None

# Header Banner
col_header1, col_header2, col_header3 = st.columns([1.5, 4, 1.5])
with col_header1:
    try:
        st.image("istestate_logo.png", use_container_width=True)
    except Exception:
        st.caption("istestate_logo.png")

with col_header2:
    st.markdown(
        """
    <div style="text-align: center; padding-top: 5px;">
        <h2 style="color: #FFFFFF; font-weight: 800; margin-bottom: 0px; font-size: 26px;">İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK</h2>
        <h3 style="color: #38BDF8; font-weight: 600; margin-top: 0px; font-size: 20px;">& MERİÇ İNŞAAT EMLAK</h3>
        <p style="color: #94A3B8; font-size: 14px; margin-top: 5px;">Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli</p>
    </div>
    """,
        unsafe_allow_html=True,
    )

with col_header3:
    try:
        st.image("meric_insaat_emlak_logo.png", use_container_width=True)
    except Exception:
        st.caption("meric_insaat_emlak_logo.png")

st.divider()

# SOL PANEL
with st.sidebar:
    st.markdown("### 📄 1. Belge Analizi & Akıllı Hafıza")

    uploaded_pdfs = st.file_uploader(
        "İmar Durumu PDF Raporlarını Yükleyin (Çoklu Seçim)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if not gemini_api_key:
        gemini_api_key = st.text_input("Gemini API Key", type="password")

    if uploaded_pdfs:
        for uploaded_pdf in uploaded_pdfs:
            if uploaded_pdf.name not in st.session_state.processed_files:
                with st.spinner(f"{uploaded_pdf.name} Analiz Ediliyor..."):
                    try:
                        with pdfplumber.open(uploaded_pdf) as pdf:
                            extracted_text = "\n".join(
                                [page.extract_text() or "" for page in pdf.pages]
                            )

                        data = None
                        if gemini_api_key:
                            data = parse_pdf_with_gemini_retry(
                                extracted_text, gemini_api_key
                            )

                        if not data:
                            data = fallback_regex_parser(extracted_text)

                        if data:
                            gelen_mahalle = clean_mahalle_name(
                                data.get("mahalle", st.session_state.mahalle)
                            )
                            for b_adi, m_listesi in BOLGE_MAHALLE_HARITASI.items():
                                for m in m_listesi:
                                    if (
                                        clean_mahalle_name(m).upper()
                                        == gelen_mahalle.upper()
                                    ):
                                        st.session_state.bolge = b_adi
                                        st.session_state.mahalle = m
                                        break

                            st.session_state.ada = str(
                                data.get("ada", st.session_state.ada)
                            )
                            st.session_state.parsel = str(
                                data.get("parsel", st.session_state.parsel)
                            )
                            st.session_state.tapu_alani = float(
                                data.get(
                                    "tapu_alani", st.session_state.tapu_alani
                                )
                            )
                            st.session_state.park_terk_alani = float(
                                data.get("park_terk_alani", 0.0)
                            )
                            
                            # Net ve Terk Mantığı Otomatik Hesaplama
                            terk_yapilmis_mi = st.session_state.terk_yapilmis
                            if terk_yapilmis_mi:
                                st.session_state.net_konut_alani = st.session_state.tapu_alani
                            else:
                                raw_net = data.get("net_konut_alani")
                                if raw_net and float(raw_net) > 0:
                                    st.session_state.net_konut_alani = float(raw_net)
                                else:
                                    # Terk yapılmamışsa, terk dışındaki kalan alan doğrudan net kullanılabilir kabul edilir
                                    st.session_state.net_konut_alani = max(0.0, st.session_state.tapu_alani - st.session_state.park_terk_alani)

                            st.session_state.net_konut_orani = (
                                (st.session_state.net_konut_alani / st.session_state.tapu_alani * 100)
                                if st.session_state.tapu_alani > 0 else 100.0
                            )

                            st.session_state.kaks = float(
                                data.get("kaks", st.session_state.kaks)
                            )
                            st.session_state.taks = float(
                                data.get("taks", st.session_state.taks)
                            )
                            st.session_state.tevhid_aktif = False

                            if data.get("imar_fonksiyonu"):
                                st.session_state.imar_fonksiyonu = str(
                                    data.get("imar_fonksiyonu")
                                ).upper()

                            db_kayit_ekle_veya_guncelle(
                                st.session_state.mahalle,
                                st.session_state.ada,
                                st.session_state.parsel,
                                st.session_state.tapu_alani,
                                st.session_state.net_konut_alani,
                                st.session_state.net_konut_orani,
                                st.session_state.park_terk_alani,
                                st.session_state.terk_yapilmis,
                                st.session_state.kaks,
                                st.session_state.taks,
                                st.session_state.imar_fonksiyonu,
                            )

                            st.session_state.processed_files.append(
                                uploaded_pdf.name
                            )
                            st.toast(
                                f"✅ {uploaded_pdf.name} işlendi!", icon="⚡"
                            )

                        time.sleep(2)

                    except Exception as e:
                        st.error(f"{uploaded_pdf.name} İşleme Hatası: {e}")
        st.rerun()

    st.markdown("---")
    st.markdown("### 📍 2. Bölge & Parsel Seçimi")

    col_a, col_p = st.columns(2)
    with col_a:
        ada = st.text_input("Ada No", value=st.session_state.ada)
    with col_p:
        parsel = st.text_input("Parsel No", value=st.session_state.parsel)

    if st.button("🔍 Hafızadan Bilgi Çek", use_container_width=True):
        hafiza_veri = db_kayit_sorgula(ada, parsel)
        if hafiza_veri:
            (
                kayitli_mahalle,
                kayitli_tapu,
                kayitli_net_konut,
                kayitli_net_oran,
                kayitli_park,
                kayitli_terk_yapilmis,
                kayitli_kaks,
                kayitli_taks,
                kayitli_imar_fonks,
            ) = hafiza_veri
            sade_kayitli_mahalle = clean_mahalle_name(kayitli_mahalle)

            bulunan_bolge = None
            for bolge_adi, mahalleler in BOLGE_MAHALLE_HARITASI.items():
                for m in mahalleler:
                    if (
                        clean_mahalle_name(m).upper()
                        == sade_kayitli_mahalle.upper()
                    ):
                        bulunan_bolge = bolge_adi
                        st.session_state.mahalle = m
                        break
                if bulunan_bolge:
                    break

            if bulunan_bolge:
                st.session_state.bolge = bulunan_bolge
            else:
                st.session_state.mahalle = sade_kayitli_mahalle

            st.session_state.tapu_alani = kayitli_tapu
            st.session_state.net_konut_alani = kayitli_net_konut
            st.session_state.net_konut_orani = kayitli_net_oran
            st.session_state.park_terk_alani = kayitli_park
            st.session_state.terk_yapilmis = bool(kayitli_terk_yapilmis)
            st.session_state.kaks = kayitli_kaks
            st.session_state.taks = kayitli_taks
            if kayitli_imar_fonks:
                st.session_state.imar_fonksiyonu = kayitli_imar_fonks

            st.session_state.ada = str(ada).strip()
            st.session_state.parsel = str(parsel).strip()
            st.session_state.tevhid_aktif = False

            st.success(
                f"✅ **Ada: {ada} / Parsel: {parsel}** eşleşti! Bölge ve Mahalle güncellendi."
            )
            st.rerun()
        else:
            st.error(f"❌ Ada: {ada} / Parsel: {parsel} için kayıt bulunamadı.")

    bolge_listesi = list(BOLGE_MAHALLE_HARITASI.keys())
    selected_bolge = st.selectbox(
        "Bölge / Semt Seçin",
        options=bolge_listesi,
        index=(
            bolge_listesi.index(st.session_state.bolge)
            if st.session_state.bolge in bolge_listesi
            else 0
        ),
    )
    st.session_state.bolge = selected_bolge

    bagli_mahalleler = BOLGE_MAHALLE_HARITASI[selected_bolge]
    current_sade_mahalle = clean_mahalle_name(st.session_state.mahalle)
    selected_mahalle_index = 0
    for idx, m in enumerate(bagli_mahalleler):
        if clean_mahalle_name(m).upper() == current_sade_mahalle.upper():
            selected_mahalle_index = idx
            break

    mahalle = st.selectbox(
        "Mahalle Seçin",
        options=bagli_mahalleler,
        index=selected_mahalle_index,
    )
    st.session_state.mahalle = mahalle

    imar_fonks_index = 0
    for idx, f in enumerate(IMAR_FONKSIYONLARI):
        if f.upper() == str(st.session_state.imar_fonksiyonu).upper():
            imar_fonks_index = idx
            break

    imar_fonksiyonu = st.selectbox(
        "İmar Fonksiyon Alanı",
        options=IMAR_FONKSIYONLARI,
        index=imar_fonks_index,
    )
    st.session_state.imar_fonksiyonu = imar_fonksiyonu

    yapi_tipolojisi = st.selectbox(
        "Mimari Yapı Tipolojisi Tercihi",
        [
            "Müstakil Villa",
            "İkiz Villa",
            "Bahçe - Çatı Dubleksi",
            "Standart Daire / Konut",
        ],
    )

    st.markdown("#### 🏊 Havuz Proje Seçenekleri")
    havuz_tercihi = st.selectbox(
        "Havuz Tipi",
        [
            "Havuzsuz",
            "Müstakil Havuzlu (Her Üniteye)",
            "Ortak Kullanım Havuzlu",
        ],
    )

    havuz_m2_birim = 0.0
    if havuz_tercihi == "Müstakil Havuzlu (Her Üniteye)":
        havuz_m2_birim = st.number_input(
            "Ünite Başı Müstakil Havuz Alanı (m²)", value=35.0, step=5.0
        )
    elif havuz_tercihi == "Ortak Kullanım Havuzlu":
        havuz_m2_birim = st.number_input(
            "Toplam Ortak Havuz Alanı (m²)", value=120.0, step=10.0
        )

    # TERK VE ARAZİ AYRIMI SEÇİMİ
    st.markdown("#### 📐 Arazi & Terk Durumu")
    terk_durumu_secimi = st.radio(
        "Arazi Terk Statüsü:",
        ["Terk Yapılmamış (Brüt Arazi)", "Terk Yapılmış (Net Arazi)"],
        index=1 if st.session_state.terk_yapilmis else 0,
        help="Terk yapılmış araziler doğrudan net kabul edilir. Terk yapılmamış arazilerde, rapordaki terk alanları düşülür; terk dışındaki alan oran ne olursa olsun kullanılabilir arsa sayılır."
    )
    terk_yapilmis = terk_durumu_secimi == "Terk Yapılmış (Net Arazi)"
    st.session_state.terk_yapilmis = terk_yapilmis

    tapu_alani = st.number_input(
        "Brüt Tapu Alanı (m²)" if not terk_yapilmis else "Net Tapu Alanı (m²)",
        value=float(st.session_state.tapu_alani),
        step=10.0,
    )
    park_terk_alani = st.number_input(
        "Park / Kamu Terk Alanı (m²)",
        value=float(st.session_state.park_terk_alani),
        step=10.0,
        disabled=terk_yapilmis
    )

    # Terk Yapılmış / Yapılmamış Mantığına Göre Net Konut Alanı Hesabı
    if terk_yapilmis:
        net_konut_alani = tapu_alani
        park_terk_alani = 0.0
    else:
        # Terk dışı alan terk oranı ne olursa olsun tam kullanılabilir arsadır
        net_konut_alani = max(0.0, tapu_alani - park_terk_alani)

    net_konut_orani = (net_konut_alani / tapu_alani * 100) if tapu_alani > 0 else 0.0
    st.caption(f"📐 Kullanılabilir Net Arsa: **{net_konut_alani:,.2f} m²** (%{net_konut_orani:.2f})")

    st.session_state.tapu_alani = tapu_alani
    st.session_state.net_konut_alani = net_konut_alani
    st.session_state.net_konut_orani = net_konut_orani
    st.session_state.park_terk_alani = park_terk_alani

    nitelik = st.selectbox("Nitelik", ["Arsa", "Bahçe", "Tarla"])

    col_k, col_t = st.columns(2)
    with col_k:
        kaks = st.number_input(
            "KAKS (Emsal)", value=float(st.session_state.kaks), step=0.05
        )
    with col_t:
        taks = st.number_input(
            "TAKS", value=float(st.session_state.taks), step=0.05
        )

    if st.button(
        "💾 Mevcut Verileri Hafızaya Kaydet", use_container_width=True
    ):
        db_kayit_ekle_veya_guncelle(
            mahalle, ada, parsel, tapu_alani, net_konut_alani, net_konut_orani, park_terk_alani, terk_yapilmis, kaks, taks, imar_fonksiyonu
        )
        st.toast("Veriler başarıyla hafızaya kaydedildi!", icon="✅")

    # TEVHİD MODÜLÜ
    st.markdown("---")
    st.markdown("### 🔗 2.1 Tevhid (Çoklu Parsel)")

    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        df_hafiza = pd.read_sql_query(
            "SELECT id, mahalle, ada, parsel, tapu_alani, net_konut_alani FROM imar_kayitlari",
            conn,
        )
        conn.close()

        if not df_hafiza.empty:
            opsiyonlar = {
                f"{row['mahalle']} | Ada:{row['ada']} / Par:{row['parsel']} (Brüt:{row['tapu_alani']}m² / Net:{row['net_konut_alani']}m²)": row[
                    "id"
                ]
                for _, row in df_hafiza.iterrows()
            }

            secilen_tevhid_kayitlari = st.multiselect(
                "Birleştirilecek Parseller:", options=list(opsiyonlar.keys())
            )

            if st.button(
                "🔗 Seçilileri Tevhid Et & Aktar", use_container_width=True
            ):
                if secilen_tevhid_kayitlari:
                    ids = [opsiyonlar[k] for k in secilen_tevhid_kayitlari]
                    birlestirilmis = get_birlesik_parsel_verisi(ids)

                    if birlestirilmis:
                        st.session_state.tapu_alani = birlestirilmis["toplam_tapu"]
                        st.session_state.net_konut_alani = birlestirilmis["net_konut_alani"]
                        st.session_state.net_konut_orani = birlestirilmis["net_konut_orani"]
                        st.session_state.park_terk_alani = birlestirilmis["park_terk_alani"]
                        st.session_state.terk_yapilmis = bool(birlestirilmis["terk_yapilmis"])
                        st.session_state.kaks = birlestirilmis["kaks"]
                        st.session_state.taks = birlestirilmis["taks"]
                        st.session_state.ada = birlestirilmis["ada"]
                        st.session_state.parsel = birlestirilmis["parsel"]

                        if birlestirilmis["mahalle"]:
                            m_sade = clean_mahalle_name(
                                birlestirilmis["mahalle"]
                            )
                            for b_k, m_v in BOLGE_MAHALLE_HARITASI.items():
                                if any(
                                    clean_mahalle_name(x).upper()
                                    == m_sade.upper()
                                    for x in m_v
                                ):
                                    st.session_state.bolge = b_k
                                    st.session_state.mahalle = m_sade
                                    break

                        if birlestirilmis["imar_fonksiyonu"]:
                            st.session_state.imar_fonksiyonu = birlestirilmis[
                                "imar_fonksiyonu"
                            ]

                        st.session_state.tevhid_aktif = True
                        st.session_state.tevhid_df = birlestirilmis["detay_df"]

                        st.toast("Tevhid verileri aktarıldı!", icon="🔗")
                        st.rerun()
        else:
            st.caption("Tevhid için hafızada parsel bulunamadı.")
    except Exception as e:
        st.warning(f"Tevhid Modülü Hatası: {e}")

    sunum_tipi = st.selectbox("Sunum Modeli", ["Satılık", "Kat Karşılığı"])

    st.markdown("---")
    st.markdown("### 💰 3. Finansal Parametreler ($ USD)")

    current_search_key = f"{mahalle}_{yapi_tipolojisi}"
    if st.session_state.last_searched_key != current_search_key:
        usd_rate = get_tcmb_usd_rate()
        market_data = (
            fetch_market_prices_via_gemini(
                mahalle, yapi_tipolojisi, gemini_api_key
            )
            if gemini_api_key
            else None
        )

        if (
            market_data
            and "maliyet_usd" in market_data
            and "satis_usd" in market_data
        ):
            st.session_state.auto_maliyet_usd = int(market_data["maliyet_usd"])
            st.session_state.auto_satis_usd = int(market_data["satis_usd"])
        else:
            maliyet_tl = (
                48000
                if yapi_tipolojisi in ["Müstakil Villa", "İkiz Villa"]
                else 38000
            )
            satis_tl = (
                185000
                if yapi_tipolojisi in ["Müstakil Villa", "İkiz Villa"]
                else 140000
            )
            st.session_state.auto_maliyet_usd = int(maliyet_tl / usd_rate)
            st.session_state.auto_satis_usd = int(satis_tl / usd_rate)

        st.session_state.last_searched_key = current_search_key

    birim_maliyeti_usd = st.number_input(
        "M² İnşaat Maliyeti ($)",
        value=st.session_state.get("auto_maliyet_usd", 1200),
        step=50,
    )
    satis_m2_fiyati_usd = st.number_input(
        "M² Satış Fiyatı ($)",
        value=st.session_state.get("auto_satis_usd", 5000),
        step=100,
    )
    kat_karsiligi_orani = (
        st.slider("Kat Karşılığı Payı (%)", 30, 60, 50)
        if sunum_tipi == "Kat Karşılığı"
        else 50
    )
    unite_m2 = st.number_input(
        "Ortalama Ünite Brüt m²", value=200, step=10
    )

# İMAR HESAPLARI (Net Kullanılabilir Arsa Odaklı İnşaat Hesabı)
net_alan = net_konut_alani
terk_str = "Terk Yapılmış (Net)" if terk_yapilmis else f"Terk Yapılmamış (Terk Sonrası Net: %{net_konut_orani:.1f})"

net_emsal_alani = net_alan * kaks
ilave_emsal_harici = net_emsal_alani * 0.30
ham_toplam_brut_insaat = net_emsal_alani * 1.30
max_taban_alani = net_alan * taks

gecici_unite_adedi = (
    int(ham_toplam_brut_insaat / unite_m2) if unite_m2 > 0 else 0
)

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
    mutaahhit_unite_adedi = (
        int(mutaahhit_payi_m2 / unite_m2) if unite_m2 > 0 else 0
    )
    arsa_sahibi_unite_adedi = (
        int(arsa_sahibi_payi_m2 / unite_m2) if unite_m2 > 0 else 0
    )
    mutaahhit_net_kar_usd = (
        mutaahhit_payi_m2 * satis_m2_fiyati_usd
    ) - toplam_insaat_maliyeti_usd
else:
    mutaahhit_net_kar_usd = (
        toplam_proje_geliri_usd - toplam_insaat_maliyeti_usd
    )

# TEVHİD BİLGİLENDİRME BANTI
if st.session_state.get("tevhid_aktif"):
    st.info(
        f"🔗 **TEVHİD (ÇOKLU PARSEL) MODU AKTİF** | Ada: `{st.session_state.ada}` | Parsel: `{st.session_state.parsel}` | Toplam Brüt Tapu: `{tapu_alani:,.2f} m²` | Net Kullanılabilir Arsa: `{net_konut_alani:,.2f} m²`"
    )
    with st.expander("🔍 Birleştirilen Parsellerin Detay Listesini Göster"):
        if st.session_state.tevhid_df is not None:
            st.dataframe(st.session_state.tevhid_df, use_container_width=True)

# ANA SEKMELER
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📐 İmar & Kapasite Analizi",
        "🏗️ Mimari Potansiyel & Havuz Detayı",
        "💰 Finansal Fizibilite ($ USD)",
        "🗄️ Sistem Hafızası",
    ]
)

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Brüt Tapu Alanı", f"{tapu_alani:,.2f} m²")
    c2.metric(
        "Kullanılabilir Net Arsa",
        f"{net_konut_alani:,.2f} m²",
        delta=terk_str,
    )
    c3.metric("Net Emsal Alanı", f"{net_emsal_alani:,.2f} m²")
    c4.metric(
        "NET KAPALI İNŞAAT",
        f"{toplam_brut_insaat:,.2f} m²",
        delta=(
            f"-{toplam_havuz_alani:,.1f} m² Havuz Payı"
            if toplam_havuz_alani > 0
            else "Havuzsuz"
        ),
    )

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### 📋 İmar Parametre Detayları")
    df_imar = pd.DataFrame(
        {
            "Parametre": [
                "Mahalle",
                "İmar Fonksiyonu",
                "Yapı Tipolojisi",
                "Terk Statüsü",
                "Havuz Durumu",
                "Park / Kamu Terk Alanı",
                "Uygulanan KAKS (Emsal)",
                "TAKS (Taban Alanı Katsayısı)",
                "Max Taban Oturumu Alanı",
                "%30 İlave Emsal Harici",
            ],
            "Değer": [
                mahalle,
                imar_fonksiyonu,
                yapi_tipolojisi,
                "Terk Yapılmış (Doğrudan Net)" if terk_yapilmis else "Terk Yapılmamış (Terk Dışı Net Kullanılabilir)",
                f"{havuz_tercihi} ({toplam_havuz_alani:,.1f} m²)",
                f"{park_terk_alani:,.2f} m²",
                f"{kaks:.2f}",
                f"{taks:.2f}",
                f"{max_taban_alani:,.2f} m²",
                f"{ilave_emsal_harici:,.2f} m²",
            ],
        }
    )
    st.table(df_imar)

with tab2:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown(
            f"#### 🏛️ Bölgesel Mimari Planlama ({imar_fonksiyonu})"
        )
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
            st.markdown(
                f"#### 🤝 Kat Karşılığı Paylaşım Modeli (%{kat_karsiligi_orani} Arsa / %{100-kat_karsiligi_orani} Müteahhit)"
            )
            st.success(f"""
            * **Arsa Sahibi Kalan Net İnşaat:** {arsa_sahibi_payi_m2:,.2f} m² (~{arsa_sahibi_unite_adedi} Ünite)
            * **Müteahhit Kalan Net İnşaat:** {mutaahhit_payi_m2:,.2f} m² (~{mutaahhit_unite_adedi} Ünite)
            """)

with tab3:
    f1, f2, f3 = st.columns(3)
    f1.metric(
        "Toplam İnşaat Maliyeti", f"${toplam_insaat_maliyeti_usd:,.0f}"
    )
    f2.metric("Toplam Proje Ciro Hacmi", f"${toplam_proje_geliri_usd:,.0f}")
    f3.metric(
        "Tahmini Net Kar / Proje Marjı", f"${mutaahhit_net_kar_usd:,.0f}"
    )

with tab4:
    st.markdown("#### 🗄️ Veri Tabanında Kayıtlı Tüm Parseller")
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        df_db = pd.read_sql_query(
            """
            SELECT id, mahalle AS Mahalle, ada AS Ada, parsel AS Parsel, 
                   imar_fonksiyonu AS 'İmar Fonksiyonu', tapu_alani AS 'Brüt Tapu (m²)', 
                   net_konut_alani AS 'Net Arsa (m²)', park_terk_alani AS 'Park/Terk (m²)',
                   CASE WHEN terk_yapilmis = 1 THEN 'Yapılmış' ELSE 'Yapılmamış' END AS 'Terk Statüsü',
                   kaks AS KAKS, taks AS TAKS 
            FROM imar_kayitlari
            """,
            conn,
        )
        conn.close()

        if not df_db.empty:
            df_db["Mahalle"] = df_db["Mahalle"].apply(clean_mahalle_name)
            st.dataframe(df_db.drop(columns=["id"]), use_container_width=True)

            st.markdown("---")
            st.markdown("#### 🗑️ Kayıt Silme İşlemi")

            options_dict = {
                f"ID: {row['id']} | {row['Mahalle']} - Ada: {row['Ada']} / Parsel: {row['Parsel']}": row[
                    "id"
                ]
                for _, row in df_db.iterrows()
            }
            selected_to_delete = st.selectbox(
                "Silmek İstediğiniz Kaydı Seçin:",
                options=list(options_dict.keys()),
            )

            if st.button(
                "❌ Seçili Kaydı Veri Tabanından Sil", type="primary"
            ):
                record_id_to_del = options_dict[selected_to_delete]
                db_kayit_sil(record_id_to_del)
                st.success("Kayıt veritabanından başarıyla silindi!")
                st.rerun()
        else:
            st.info("Sistem hafızasında henüz kayıtlı veri bulunmuyor.")
    except Exception as e:
        st.error(f"Veritabanı listeleme hatası: {e}")


# PDF Oluşturma (BRÜT / NET TERK DESTEKLİ)
def yatay_kurumsal_pdf_olustur():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        rightMargin=20,
        leftMargin=20,
        topMargin=20,
        bottomMargin=20,
    )
    story = []

    banner_title = ParagraphStyle(
        "BTitle",
        fontName=USE_FONT_BOLD,
        fontSize=11,
        textColor=colors.white,
        alignment=1,
        leading=14,
    )
    th_style = ParagraphStyle(
        "TH",
        fontName=USE_FONT_BOLD,
        fontSize=7.5,
        textColor=colors.white,
        alignment=1,
        leading=9,
    )
    td_style = ParagraphStyle(
        "TD",
        fontName=USE_FONT,
        fontSize=8,
        textColor=colors.HexColor("#1E293B"),
        alignment=1,
        leading=10,
    )
    td_bold = ParagraphStyle(
        "TDBold",
        fontName=USE_FONT_BOLD,
        fontSize=8,
        textColor=colors.HexColor("#0F172A"),
        alignment=1,
        leading=10,
    )
    section_title = ParagraphStyle(
        "SecTitle",
        fontName=USE_FONT_BOLD,
        fontSize=9,
        textColor=colors.HexColor("#1B2A47"),
        spaceAfter=4,
    )
    footer_style = ParagraphStyle(
        "Footer",
        fontName=USE_FONT,
        fontSize=7.5,
        textColor=colors.HexColor("#475569"),
        leading=11,
    )

    try:
        img_ist = RLImage("istestate_logo.png", width=140, height=42)
        img_mer = RLImage("meric_insaat_emlak_logo.png", width=150, height=42)

        box_ist = Table([[img_ist]], colWidths=[146])
        box_ist.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )

        box_mer = Table([[img_mer]], colWidths=[156])
        box_mer.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )

        banner_text = Paragraph(
            f"<b>{tr_fix('İSTESTATE & MERİÇ İNŞAAT EMLAK')}</b><br/>"
            f"<font size=8 color='#E2E8F0'>{tr_fix('DETAYLI İMAR, MİMARİ POTANSİYEL VE FİNANSAL FİZİBİLİTE RAPORU')}</font>",
            banner_title,
        )

        banner_table = Table(
            [[box_ist, banner_text, box_mer]], colWidths=[156, 490, 156]
        )
        banner_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#1B2A47")),
                ("ALIGN", (0, 0), (0, 0), "LEFT"),
                ("ALIGN", (1, 0), (1, 0), "CENTER"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        story.append(banner_table)
        story.append(Spacer(1, 10))
    except Exception:
        pass

    # TABLO 1: İMAR VE KAPASİTE
    story.append(
        Paragraph(
            tr_fix("1. PARSEL BAZLI İMAR VE KAPASİTE TABLOSU"), section_title
        )
    )
    headers_t1 = [
        Paragraph(tr_fix("MAHALLE"), th_style),
        Paragraph(tr_fix("ADA"), th_style),
        Paragraph(tr_fix("PARSEL"), th_style),
        Paragraph(tr_fix("BRÜT ALAN (M²)"), th_style),
        Paragraph(tr_fix("NET ARSA (M²)"), th_style),
        Paragraph(tr_fix("PARK/TERK (M²)"), th_style),
        Paragraph(tr_fix("FONKSİYON"), th_style),
        Paragraph(tr_fix("KAKS"), th_style),
        Paragraph(tr_fix("HAM İNŞAAT (M²)"), th_style),
        Paragraph(tr_fix("NET KAPALI İNŞAAT (M²)"), th_style),
    ]
    row_t1 = [
        Paragraph(tr_fix(clean_mahalle_name(mahalle)), td_style),
        Paragraph(tr_fix(str(ada)), td_style),
        Paragraph(tr_fix(str(parsel)), td_style),
        Paragraph(f"{tapu_alani:,.2f}", td_style),
        Paragraph(f"{net_konut_alani:,.2f}", td_style),
        Paragraph(f"{park_terk_alani:,.2f}", td_style),
        Paragraph(tr_fix(imar_fonksiyonu), td_style),
        Paragraph(f"{kaks:.2f}", td_style),
        Paragraph(f"{ham_toplam_brut_insaat:,.2f}", td_style),
        Paragraph(f"{toplam_brut_insaat:,.2f}", td_bold),
    ]
    table1 = Table(
        [headers_t1, row_t1],
        colWidths=[75, 45, 45, 80, 80, 75, 115, 40, 95, 102],
    )
    table1.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B2A47")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
        ])
    )
    story.append(table1)
    story.append(Spacer(1, 10))

    # TABLO 2: MİMARİ POTANSİYEL
    story.append(
        Paragraph(
            tr_fix("2. MİMARİ POTANSİYEL VE HAVUZ YAPILAŞMA DETAYI"),
            section_title,
        )
    )
    headers_t2 = [
        Paragraph(tr_fix("YAPI TİPOLOJİSİ"), th_style),
        Paragraph(tr_fix("HAVUZ TİPİ VE ALANI"), th_style),
        Paragraph(tr_fix("ORTALAMA ÜNİTE BRÜT M²"), th_style),
        Paragraph(tr_fix("TAHMİNİ ÜNİTE ADEDİ"), th_style),
        Paragraph(tr_fix("TAKS (TABAN KATSAYISI)"), th_style),
        Paragraph(tr_fix("MAX TABAN OTURUMU (M²)"), th_style),
    ]
    row_t2 = [
        Paragraph(tr_fix(yapi_tipolojisi), td_style),
        Paragraph(
            tr_fix(f"{havuz_tercihi} ({toplam_havuz_alani:,.1f} m²)"), td_style
        ),
        Paragraph(f"{unite_m2} m²", td_style),
        Paragraph(f"~{toplam_unite_adedi} Adet", td_bold),
        Paragraph(f"{taks:.2f}", td_style),
        Paragraph(f"{max_taban_alani:,.2f} m²", td_style),
    ]
    table2 = Table(
        [headers_t2, row_t2], colWidths=[150, 150, 110, 110, 140, 142]
    )
    table2.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2A3B5C")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
        ])
    )
    story.append(table2)
    story.append(Spacer(1, 10))

    # TABLO 3: FİNANSAL FİZİBİLİTE
    story.append(
        Paragraph(
            tr_fix("3. FİNANSAL FİZİBİLİTE ANALİZİ ($ USD)"), section_title
        )
    )
    headers_t3 = [
        Paragraph(tr_fix("M² İNŞAAT MALİYETİ ($)"), th_style),
        Paragraph(tr_fix("TOPLAM İNŞAAT MALİYETİ ($)"), th_style),
        Paragraph(tr_fix("M² SATIŞ FİYATI ($)"), th_style),
        Paragraph(tr_fix("TOPLAM PROJE CİROSU ($)"), th_style),
        Paragraph(tr_fix("TAHMİNİ NET KAR MARJI ($)"), th_style),
    ]
    row_t3 = [
        Paragraph(f"${birim_maliyeti_usd:,.0f}", td_style),
        Paragraph(f"${toplam_insaat_maliyeti_usd:,.0f}", td_style),
        Paragraph(f"${satis_m2_fiyati_usd:,.0f}", td_style),
        Paragraph(f"${toplam_proje_geliri_usd:,.0f}", td_style),
        Paragraph(f"${mutaahhit_net_kar_usd:,.0f}", td_bold),
    ]
    table3 = Table(
        [headers_t3, row_t3], colWidths=[150, 160, 150, 170, 172]
    )
    table3.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#F8FAFC")),
        ])
    )
    story.append(table3)
    story.append(Spacer(1, 10))

    # TABLO 4: KAT KARŞILIĞI (Opsiyonel)
    if sunum_tipi == "Kat Karşılığı":
        story.append(
            Paragraph(
                tr_fix(
                    f"4. KAT KARŞILIĞI PAYLAŞIM DETAYLARI (%{kat_karsiligi_orani} ARSA / %{100-kat_karsiligi_orani} MÜTEAHHİT)"
                ),
                section_title,
            )
        )
        headers_t4 = [
            Paragraph(tr_fix("PAYDAŞ"), th_style),
            Paragraph(tr_fix("PAY ORANI (%)"), th_style),
            Paragraph(tr_fix("KALAN NET İNŞAAT ALANI (M²)"), th_style),
            Paragraph(tr_fix("TAHMİNİ BAĞIMSIZ BÖLÜM ADEDİ"), th_style),
        ]
        row_t4_1 = [
            Paragraph(tr_fix("Arsa Sahibi Payı"), td_style),
            Paragraph(f"%{kat_karsiligi_orani}", td_style),
            Paragraph(f"{arsa_sahibi_payi_m2:,.2f} m²", td_style),
            Paragraph(f"~{arsa_sahibi_unite_adedi} Adet", td_bold),
        ]
        row_t4_2 = [
            Paragraph(tr_fix("Müteahhit Payı"), td_style),
            Paragraph(f"%{100-kat_karsiligi_orani}", td_style),
            Paragraph(f"{mutaahhit_payi_m2:,.2f} m²", td_style),
            Paragraph(f"~{mutaahhit_unite_adedi} Adet", td_bold),
        ]
        table4 = Table(
            [headers_t4, row_t4_1, row_t4_2], colWidths=[180, 150, 230, 242]
        )
        table4.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334155")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F8FAFC")),
            ])
        )
        story.append(table4)
        story.append(Spacer(1, 10))

    iletisim = (
        tr_fix(
            "<b>İstestate Meriç Gayrimenkul Danışmanlık & Meriç İnşaat Emlak</b> | "
        )
        + tr_fix(
            "Umutcan K. MERİÇ (0539 451 61 61) - Süleyman MERİÇ (0532 695 10"
            " 83)<br/>"
        )
        + tr_fix(
            "<b>Adres:</b> Çiftlik Mah. Çavuşbaşı Cumhuriyet Cad. No:171/3"
            " Beykoz/İSTANBUL"
        )
    )
    story.append(Paragraph(iletisim, footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer


clean_mahalle_file = (
    re.sub(r"[^\w\s-]", "", clean_mahalle_name(mahalle))
    .strip()
    .replace(" ", "_")
)
kurumsal_dosya_adi = f"ISTESTATE_MERIC_Fizibilite_Raporu_{clean_mahalle_file}_{ada}_{parsel}_2026.pdf"

st.divider()
st.download_button(
    label="📄 Kurumsal PDF Raporunu İndir ($ USD)",
    data=yatay_kurumsal_pdf_olustur(),
    file_name=kurumsal_dosya_adi,
    mime="application/pdf",
)
