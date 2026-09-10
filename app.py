import json
import re
import sqlite3
import google.generativeai as genai
import pandas as pd
import pdfplumber
import streamlit as st

# =========================================================
# 1. MEVCUT VERİTABANI SİSTEMİ (BOZULMADAN KORUNDU)
# =========================================================


def init_db():
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
            kaks REAL,
            taks REAL,
            imar_fonksiyonu TEXT,
            UNIQUE(mahalle, ada, parsel)
        )
    """
    )
    conn.commit()
    conn.close()


def db_kayit_ekle_veya_guncelle(
    mahalle, ada, parsel, tapu_alani, kaks, taks, imar_fonksiyonu
):
    conn = sqlite3.connect("imar_hafizasi.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO imar_kayitlari (mahalle, ada, parsel, tapu_alani, kaks, taks, imar_fonksiyonu)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(mahalle, ada, parsel) DO UPDATE SET
            tapu_alani=excluded.tapu_alani,
            kaks=excluded.kaks,
            taks=excluded.taks,
            imar_fonksiyonu=excluded.imar_fonksiyonu
    """,
        (mahalle, ada, parsel, tapu_alani, kaks, taks, imar_fonksiyonu),
    )
    conn.commit()
    conn.close()


# =========================================================
# YENİ EKLENEN BAĞIMSIZ TEVHİD HESAPLAMA FONKSİYONU
# (Eski sisteme zarar vermez, sadece verileri okur ve harmanlar)
# =========================================================


def get_birlesik_parsel_verisi(record_ids):
    """Mevcut DB'den seçilen parsel id'lerini çekerek ağırlıklı ortalama hesaplar."""
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

    # Metrekare ağırlıklı ortalama hesabı
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
        "mahalle": df["mahalle"].iloc[0] if not df.empty else "-",
        "toplam_tapu": toplam_tapu,
        "kaks": agirlikli_kaks,
        "taks": agirlikli_taks,
        "detay_df": df,
    }


# DB Kurulumu
init_db()

# =========================================================
# 2. STREAMLIT ARAYÜZÜ VE SESSION STATE
# =========================================================
st.set_page_config(
    page_title="İmar Analiz Portalı", layout="wide", page_icon="🏗️"
)

# Eski sistem state değerleri
if "tapu_alani" not in st.session_state:
    st.session_state.tapu_alani = 1000.0
if "kaks" not in st.session_state:
    st.session_state.kaks = 1.00
if "taks" not in st.session_state:
    st.session_state.taks = 0.30
if "ada" not in st.session_state:
    st.session_state.ada = "-"
if "parsel" not in st.session_state:
    st.session_state.parsel = "-"

# Yeni eklenen modül için pasif kontrol state'i
if "tevhid_aktif" not in st.session_state:
    st.session_state.tevhid_aktif = False
if "tevhid_df" not in st.session_state:
    st.session_state.tevhid_df = None

# =========================================================
# 3. SOL PANEL (SIDEBAR) - ESKİ YAPININ ALTINA YENİ EKLEME
# =========================================================
with st.sidebar:
    st.header("⚙️ Ayarlar & Veri Yükleme")
    gemini_api_key = st.text_input("Gemini API Key", type="password")

    st.markdown("---")
    # ESKİ SİSTEM: TEKİL PDF YÜKLEME
    st.subheader("📄 Tekil İmar PDF Yükle")
    uploaded_pdf = st.file_uploader(
        "İmar Durumu PDF", type=["pdf"], key="tekil_pdf"
    )

    if uploaded_pdf and gemini_api_key:
        if st.button("PDF'i Analiz Et ve Kaydet"):
            try:
                with pdfplumber.open(uploaded_pdf) as pdf:
                    text = "\n".join(
                        [page.extract_text() or "" for page in pdf.pages]
                    )

                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")
                prompt = f"JSON döndür: mahalle, ada, parsel, tapu_alani, kaks, taks. Metin: {text[:4000]}"
                res = model.generate_content(prompt)
                clean_j = re.search(r"\{.*\}", res.text, re.DOTALL)

                if clean_j:
                    data = json.loads(clean_j.group())
                    db_kayit_ekle_veya_guncelle(
                        str(data.get("mahalle", "-")),
                        str(data.get("ada", "-")),
                        str(data.get("parsel", "-")),
                        float(data.get("tapu_alani", 0)),
                        float(data.get("kaks", 0)),
                        float(data.get("taks", 0)),
                        "KONUT",
                    )
                    st.session_state.tapu_alani = float(
                        data.get("tapu_alani", 1000)
                    )
                    st.session_state.kaks = float(data.get("kaks", 1.0))
                    st.session_state.taks = float(data.get("taks", 0.3))
                    st.session_state.ada = str(data.get("ada", "-"))
                    st.session_state.parsel = str(data.get("parsel", "-"))
                    st.session_state.tevhid_aktif = False
                    st.success("Kayıt Başarılı!")
                    st.rerun()
            except Exception as e:
                st.error(f"Hata: {e}")

    # -----------------------------------------------------
    # YENİ SİSTEM: ÇOKLU PARSEL / TEVHİD EKLENTİSİ
    # (Eski kodlara müdahale etmeden alt tarafa paralel eklendi)
    # -----------------------------------------------------
    st.markdown("---")
    st.subheader("🔗 Çoklu Parsel (Tevhid) Birleştir")

    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        df_kayitlar = pd.read_sql_query(
            "SELECT id, mahalle, ada, parsel, tapu_alani FROM imar_kayitlari",
            conn,
        )
        conn.close()

        if not df_kayitlar.empty:
            secenekler = {
                f"{row['mahalle']} - Ada:{row['ada']} / Par:{row['parsel']} ({row['tapu_alani']}m²)": row[
                    "id"
                ]
                for _, row in df_kayitlar.iterrows()
            }

            secilenler = st.multiselect(
                "Tevhid Edilecek Parseller:", options=list(secenekler.keys())
            )

            if st.button("🔗 Seçili Parselleri Hesaplamaya Aktar"):
                if secilenler:
                    secilen_ids = [secenekler[k] for k in secilenler]
                    birlestirilmis = get_birlesik_parsel_verisi(secilen_ids)

                    if birlestirilmis:
                        # Eski sistemin session_state verilerini günceller
                        st.session_state.tapu_alani = birlestirilmis[
                            "toplam_tapu"
                        ]
                        st.session_state.kaks = birlestirilmis["kaks"]
                        st.session_state.taks = birlestirilmis["taks"]
                        st.session_state.ada = birlestirilmis["ada"]
                        st.session_state.parsel = birlestirilmis["parsel"]

                        # Tevhid gösterge durumları
                        st.session_state.tevhid_aktif = True
                        st.session_state.tevhid_df = birlestirilmis["detay_df"]

                        st.success("Tevhid verileri aktarıldı!")
                        st.rerun()
        else:
            st.caption("Hafızada henüz parsel bulunmuyor.")
    except Exception as e:
        st.warning(f"DB Okuma Hatası: {e}")

# =========================================================
# 4. MEVCUT ANA EKRAN & HESAPLAMALAR (BOZULMADAN KORUNDU)
# =========================================================
st.title("🏗️ İmar & Kat Karşılığı Proje Hesabı")

# Eğer çoklu parsel seçildiyse üstte bilgilendirme bandı gösterir
if st.session_state.get("tevhid_aktif"):
    st.info(
        f"🔗 **TEVHİD (BİRLEŞTİRİLMİŞ PARSEL) MODU** | Seçilen Adalar: `{st.session_state.ada}` | Parseller: `{st.session_state.parsel}`"
    )
    with st.expander("Birleştirilen Parsellerin Listesi"):
        st.dataframe(st.session_state.tevhid_df, use_container_width=True)

# Girdi Değerleri (Eski sistem parametreleriniz)
col1, col2, col3, col4 = st.columns(4)
with col1:
    tapu_alani = st.number_input(
        "Arsa Alanı (m²)",
        value=float(st.session_state.tapu_alani),
        key="input_tapu",
    )
with col2:
    kaks = st.number_input(
        "KAKS (Emsal)",
        value=float(st.session_state.kaks),
        format="%.2f",
        key="input_kaks",
    )
with col3:
    taks = st.number_input(
        "TAKS",
        value=float(st.session_state.taks),
        format="%.2f",
        key="input_taks",
    )
with col4:
    net_orani = st.slider("Net Terk Oranı (%)", 0, 45, 30)

st.markdown("---")

# Hesaplamalar
net_arazi = tapu_alani * (1 - (net_orani / 100))
toplam_insaat = net_arazi * kaks * 1.30  # %30 emsal harici dahil
oturum_alani = net_arazi * taks

m1, m2, m3, m4 = st.columns(4)
m1.metric("Net Arazi", f"{net_arazi:,.2f} m²")
m2.metric("Oturum Alanı", f"{oturum_alani:,.2f} m²")
m3.metric("Hesaplanan Emsal", f"{kaks:.2f}")
m4.metric("Toplam İnşaat Alanı", f"{toplam_insaat:,.2f} m²")

st.markdown("---")

# Kat Karşılığı Paylaşımı
st.subheader("🏠 Kat Karşılığı Paylaşımı")
oran = st.slider("Arsa Payı Oranı (%)", 30, 70, 50) / 100.0

col_mutesahhit, col_arsa = st.columns(2)
col_mutesahhit.success(
    f"Müteahhit Payı (%{int((1-oran)*100)}): **{toplam_insaat * (1-oran):,.2f} m²**"
)
col_arsa.warning(
    f"Arsa Sahibi Payı (%{int(oran*100)}): **{toplam_insaat * oran:,.2f} m²**"
)
