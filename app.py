import json
import re
import sqlite3
import google.generativeai as genai
import pandas as pd
import pdfplumber
import streamlit as st

# ---------------------------------------------------------
# 1. VERİTABANI KURULUMU VE YARDIMCI FONKSİYONLAR
# ---------------------------------------------------------


def init_db():
    """SQLite veritabanını ve tabloyu oluşturur."""
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
    """Veritabanına parsel kaydeder veya günceller."""
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


def db_coklu_parsel_sorgula(record_ids):
    """Seçilen parsel ID'lerini birleştirerek toplam alan ve ağırlıklı KAKS/TAKS hesaplar."""
    if not record_ids:
        return None
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        placeholders = ",".join(["?"] * len(record_ids))
        query = f"SELECT id, mahalle, ada, parsel, tapu_alani, kaks, taks, imar_fonksiyonu FROM imar_kayitlari WHERE id IN ({placeholders})"
        df = pd.read_sql_query(query, conn, params=record_ids)
        conn.close()

        if df.empty:
            return None

        # Toplam Tapu Alanı
        toplam_tapu = df["tapu_alani"].sum()

        # Ağırlıklı Ortalamalar (Metrekareye göre KAKS ve TAKS hesabı)
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

        # Adaları ve parselleri metin olarak birleştirme
        ozet_ada = ", ".join(df["ada"].astype(str).unique())
        ozet_parsel = ", ".join(df["parsel"].astype(str).unique())
        ozet_mahalle = df["mahalle"].iloc[0]
        ozet_fonksiyon = " / ".join(df["imar_fonksiyonu"].dropna().unique())

        return {
            "mahalle": ozet_mahalle,
            "ada": ozet_ada,
            "parsel": ozet_parsel,
            "toplam_tapu": toplam_tapu,
            "kaks": agirlikli_kaks,
            "taks": agirlikli_taks,
            "imar_fonksiyonu": ozet_fonksiyon,
            "parsel_sayisi": len(df),
            "detay_df": df,
        }
    except Exception as e:
        st.error(f"Çoklu parsel okuma hatası: {e}")
        return None


# DB Başlat
init_db()

# ---------------------------------------------------------
# 2. STREAMLIT ARAYÜZ YAPILANDIRMASI
# ---------------------------------------------------------
st.set_page_config(
    page_title="Çoklu Parsel & İmar Analiz Portalı",
    layout="wide",
    page_icon="🏗️",
)

st.title("🏗️ Çoklu Parsel (Tevhid) ve Kat Karşılığı Proje Analizi")

# Session State Tanımlamaları
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
if "mahalle" not in st.session_state:
    st.session_state.mahalle = "-"
if "imar_fonksiyonu" not in st.session_state:
    st.session_state.imar_fonksiyonu = "KONUT ALANI"
if "coklu_parsel_aktif" not in st.session_state:
    st.session_state.coklu_parsel_aktif = False
if "secilen_detay_df" not in st.session_state:
    st.session_state.secilen_detay_df = None

# ---------------------------------------------------------
# 3. SOL PANEL (SIDEBAR) - PDF YÜKLEME VE ÇOKLU SEÇİM
# ---------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Veri Girişi ve Hafıza")
    gemini_api_key = st.text_input(
        "Gemini API Key", type="password", help="API Anahtarınızı giriniz."
    )

    st.markdown("---")
    st.subheader("📄 1. Çoklu PDF Yükleme")
    uploaded_pdfs = st.file_uploader(
        "İmar Durumu PDF'lerini Seçin", type=["pdf"], accept_multiple_files=True
    )

    if uploaded_pdfs and gemini_api_key:
        if st.button("⚡ Tüm PDF'leri Analiz Et ve Kaydet"):
            with st.spinner("PDF'ler Gemini AI ile işleniyor..."):
                genai.configure(api_key=gemini_api_key)
                model = genai.GenerativeModel("gemini-1.5-flash")

                basarili_sayisi = 0
                for pdf_file in uploaded_pdfs:
                    try:
                        with pdfplumber.open(pdf_file) as pdf:
                            extracted_text = "\n".join(
                                [
                                    page.extract_text() or ""
                                    for page in pdf.pages
                                ]
                            )

                        prompt = f"""
                        Aşağıdaki imar belgesi metninden bilgileri ayıkla ve SADECE geçerli bir JSON objesi olarak döndür.
                        Gerekli alanlar:
                        - mahalle (string)
                        - ada (string)
                        - parsel (string)
                        - tapu_alani (float/number)
                        - kaks (float/number)
                        - taks (float/number)
                        - imar_fonksiyonu (string)

                        Metin:
                        {extracted_text[:4000]}
                        """

                        response = model.generate_content(prompt)
                        clean_json = re.search(
                            r"\{.*\}", response.text, re.DOTALL
                        )

                        if clean_json:
                            data = json.loads(clean_json.group())
                            db_kayit_ekle_veya_guncelle(
                                str(data.get("mahalle", "Bilinmiyor")),
                                str(data.get("ada", "-")),
                                str(data.get("parsel", "-")),
                                float(data.get("tapu_alani", 0)),
                                float(data.get("kaks", 0)),
                                float(data.get("taks", 0)),
                                str(
                                    data.get("imar_fonksiyonu", "KONUT ALANI")
                                ),
                            )
                            basarili_sayisi += 1
                    except Exception as e:
                        st.error(f"{pdf_file.name} işlenirken hata oluştu: {e}")

                if basarili_sayisi > 0:
                    st.success(
                        f"{basarili_sayisi} adet PDF başarıyla kaydoldu!"
                    )
                    st.rerun()

    st.markdown("---")
    st.subheader("🔗 2. Hafızadan Çoklu Parsel Birleştir")

    # DB kayıtlarını listeleme
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        df_kayitlar = pd.read_sql_query(
            "SELECT id, mahalle, ada, parsel, tapu_alani FROM imar_kayitlari",
            conn,
        )
        conn.close()

        if not df_kayitlar.empty:
            secenekler = {
                f"{row['mahalle']} - Ada: {row['ada']} / Par: {row['parsel']} ({row['tapu_alani']} m²)": row[
                    "id"
                ]
                for _, row in df_kayitlar.iterrows()
            }

            secilen_parseller = st.multiselect(
                "Tevhid edilecek parselleri seçin:",
                options=list(secenekler.keys()),
            )

            if st.button("🔗 Seçili Parselleri Birleştir"):
                if secilen_parseller:
                    secilen_ids = [secenekler[k] for k in secilen_parseller]
                    birlestirilmis_veri = db_coklu_parsel_sorgula(secilen_ids)

                    if birlestirilmis_veri:
                        st.session_state.mahalle = birlestirilmis_veri["mahalle"]
                        st.session_state.ada = birlestirilmis_veri["ada"]
                        st.session_state.parsel = birlestirilmis_veri["parsel"]
                        st.session_state.tapu_alani = birlestirilmis_veri[
                            "toplam_tapu"
                        ]
                        st.session_state.kaks = birlestirilmis_veri["kaks"]
                        st.session_state.taks = birlestirilmis_veri["taks"]
                        st.session_state.imar_fonksiyonu = birlestirilmis_veri[
                            "imar_fonksiyonu"
                        ]
                        st.session_state.coklu_parsel_aktif = True
                        st.session_state.secilen_detay_df = birlestirilmis_veri[
                            "detay_df"
                        ]

                        st.success("Parseller başarıyla birleştirildi!")
                        st.rerun()
                else:
                    st.warning("Lütfen en az bir parsel seçin.")
        else:
            st.info("Hafızada henüz kayıtlı parsel bulunmuyor.")
    except Exception as e:
        st.error(f"DB listeleme hatası: {e}")

# ---------------------------------------------------------
# 4. ANA EKRAN VE HESAPLAMA SEKMELERİ
# ---------------------------------------------------------
tab1, tab2 = st.tabs(
    ["📊 İmar & Kapasite Analizi", "💾 Veritabanı Kayıt Liste"]
)

with tab1:
    # Çoklu Parsel Modu Uyarısı
    if st.session_state.get("coklu_parsel_aktif"):
        st.info(
            f"🔗 **TEVHİD (ÇOKLU PARSEL) MODU AKTİF** | Birleştirilen Adalar: `{st.session_state.ada}` | Parseller: `{st.session_state.parsel}`"
        )
        with st.expander("Birleştirilen Parsellerin Detay Tablosu"):
            st.dataframe(
                st.session_state.secilen_detay_df, use_container_width=True
            )

    # Parametre Giriş / Düzenleme Alanı
    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        tapu_alani = st.number_input(
            "Toplam Brüt Arsa Alanı (m²)",
            value=float(st.session_state.tapu_alani),
            step=50.0,
        )
    with col_b:
        kaks = st.number_input(
            "KAKS (Emsal)",
            value=float(st.session_state.kaks),
            step=0.05,
            format="%.2f",
        )
    with col_c:
        taks = st.number_input(
            "TAKS",
            value=float(st.session_state.taks),
            step=0.05,
            format="%.2f",
        )
    with col_d:
        net_orani = st.slider("Net Terk Oranı (%)", 0, 45, 30)

    st.markdown("---")

    # İmar & Proje Metraj Hesaplamaları
    net_arazi = tapu_alani * (1 - (net_orani / 100))
    emsal_harici_katsayi = 1.30  # %30 emsal harici alan hakkı
    toplam_insaat_alani = net_arazi * kaks * emsal_harici_katsayi
    oturum_alani = net_arazi * taks

    # Özet Metrikler
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net Arzi Alanı", f"{net_arazi:,.2f} m²")
    m2.metric("Oturum Alanı (TAKS)", f"{oturum_alani:,.2f} m²")
    m3.metric("Ağırlıklı Emsal (KAKS)", f"{kaks:.2f}")
    m4.metric("Satılabilir / Toplam İnşaat", f"{toplam_insaat_alani:,.2f} m²")

    st.markdown("---")
    st.subheader("🏠 Kat Karşılığı Paylaşım Hesaplayıcı")
    kat_karsiligi_orani = (
        st.slider("Arsa Payı / Kat Karşılığı Oranı (%)", 30, 70, 50) / 100.0
    )

    mutesahhit_alani = toplam_insaat_alani * (1 - kat_karsiligi_orani)
    arsa_sahibi_alani = toplam_insaat_alani * kat_karsiligi_orani

    col1, col2 = st.columns(2)
    with col1:
        st.success(
            f"🏗️ **Müteahhit Payı (%{int((1-kat_karsiligi_orani)*100)}):** {mutesahhit_alani:,.2f} m²"
        )
    with col2:
        st.warning(
            f"🔑 **Arsa Sahibi Payı (%{int(kat_karsiligi_orani*100)}):** {arsa_sahibi_alani:,.2f} m²"
        )

with tab2:
    st.subheader("📚 Veritabanında Kayıtlı Tüm İmar Durumları")
    try:
        conn = sqlite3.connect("imar_hafizasi.db")
        df_tum_kayitlar = pd.read_sql_query(
            "SELECT * FROM imar_kayitlari ORDER BY id DESC", conn
        )
        conn.close()

        if not df_tum_kayitlar.empty:
            st.dataframe(df_tum_kayitlar, use_container_width=True)
        else:
            st.info("Kayıtlı veri bulunamadı.")
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
