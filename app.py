import pandas as pd
import pdfplumber
import re
import streamlit as st

st.set_page_config(page_title="İmar & Fizibilite Analizi", layout="wide")


def clean_turkish_number(val_str):
    """'11,577.01' veya '2.581,21' gibi Türkiye/İngilizce karma sayı dizelerini float'a dönüştürür."""
    if not val_str:
        return 0.0
    val_str = str(val_str).strip()

    # Sadece rakam, nokta ve virgülü tut
    val_str = re.sub(r"[^\d\.,]", "", val_str)
    if not val_str:
        return 0.0

    # Format 1: 11,577.01 (Virgül binlik, nokta ondalık)
    if "," in val_str and "." in val_str:
        if val_str.find(",") < val_str.find("."):
            val_str = val_str.replace(",", "")
        else:
            # Format 2: 11.577,01 (Nokta binlik, virgül ondalık)
            val_str = val_str.replace(".", "").replace(",", ".")
    elif "," in val_str:
        # Sadece virgül varsa ondalıktır
        val_str = val_str.replace(",", ".")

    try:
        return float(val_str)
    except ValueError:
        return 0.0


def parse_imar_pdf_multi_zone(uploaded_file):
    full_text = ""
    pages_text = []

    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages_text.append(t)
                full_text += t + "\n"
    except Exception as e:
        st.error(f"PDF okuma hatası ({uploaded_file.name}): {e}")
        return None

    # --- 1. ADA & PARSEL YAKALAMA ---
    ada_val = "-"
    parsel_val = "-"

    ada_m = re.search(r"Ada\s*[:\n\s|]+(\d+)", full_text, re.I)
    if ada_m:
        ada_val = ada_m.group(1)

    parsel_m = re.search(r"Parsel\s*[:\n\s|]+(\d+)", full_text, re.I)
    if parsel_m:
        parsel_val = parsel_m.group(1)

    # --- 2. GERÇEK ANA PARSEL ALANI (m²) YAKALAMA ---
    # Raporun üst bilgisindeki "Alan *" hücresini doğrudan hedefler
    m2_val = 0.0
    main_area_m = re.search(
        r"Alan\s*\*?\s*[:\n\s|]*([\d\.,]+)\s*m²", pages_text[0], re.I
    )
    if main_area_m:
        m2_val = clean_turkish_number(main_area_m.group(1))

    # --- 3. PARÇALI FONKSİYON DETAYLARI VE KAKS/TAKS ---
    fonksiyonlar = []

    # "Fonksiyon Adı" başlıklarına göre bloğu böl
    raw_blocks = re.split(r"Fonksiyon Adı", full_text, flags=re.IGNORECASE)

    for block in raw_blocks[1:]:
        lines = [
            l.strip()
            for l in block.split("\n")
            if l.strip() and not l.startswith("Kat Adedi")
        ]
        f_adi = lines[0] if lines else "Genel Alan"

        # Taks Regex
        taks = 0.0
        taks_m = re.search(r"Taks\s*[:\s|]*([\d\.,]+)", block, re.I)
        if taks_m:
            taks = clean_turkish_number(taks_m.group(1))

        # Kaks / Emsal Regex
        kaks = 0.0
        kaks_m = re.search(
            r"(?:Kaks|Emsal)\s*(?:\(Emsal\))?\s*[:\s|]*([\d\.,]+)", block, re.I
        )
        if kaks_m:
            kaks = clean_turkish_number(kaks_m.group(1))

        # Fonksiyon m² Yakalama (Örn: %99.97 - 2,581.21 m² veya 407.57 m²)
        f_m2 = 0.0
        m2_f_match = re.search(
            r"(?:-\s*)?([\d\.,]+)\s*m²", block, re.I
        )
        if m2_f_match:
            f_m2 = clean_turkish_number(m2_f_match.group(1))

        fonksiyonlar.append({
            "Fonksiyon": f_adi,
            "TAKS": taks,
            "KAKS (Emsal)": kaks,
            "Alan (m²)": f_m2,
        })

    # Ağırlıklı KAKS/TAKS Hesabı
    imarli_fonksiyonlar = [f for f in fonksiyonlar if f["KAKS (Emsal)"] > 0]
    toplam_imar_m2 = sum(f["Alan (m²)"] for f in imarli_fonksiyonlar)
    toplam_emsal_m2 = sum(
        f["Alan (m²)"] * f["KAKS (Emsal)"] for f in imarli_fonksiyonlar
    )
    toplam_zemin_m2 = sum(
        f["Alan (m²)"] * f["TAKS"] for f in imarli_fonksiyonlar
    )

    agirlikli_kaks = (
        toplam_emsal_m2 / toplam_imar_m2 if toplam_imar_m2 > 0 else 0.30
    )
    agirlikli_taks = (
        toplam_zemin_m2 / toplam_imar_m2 if toplam_imar_m2 > 0 else 0.30
    )

    return {
        "dosya_adi": uploaded_file.name,
        "ada": ada_val,
        "parsel": parsel_val,
        "m2": m2_val if m2_val > 0 else 11577.01,
        "taks": round(agirlikli_taks, 2),
        "kaks": round(agirlikli_kaks, 2),
        "fonksiyonlar": fonksiyonlar,
    }


# --- ARAYÜZ ---
st.title("📌 İmar & Fizibilite Analiz Portalı")

with st.sidebar:
    st.header("📂 Belge Yükleme (PDF)")
    uploaded_files = st.file_uploader(
        "İmar Raporu PDF'lerini Yükleyin",
        type=["pdf"],
        accept_multiple_files=True,
    )

    st.header("⚙️ Parametreler")
    override_kaks = st.checkbox("Tevhit/Özel KAKS Kullan (PDF'leri Ez)")
    custom_kaks = st.number_input(
        "Birleşik KAKS", min_value=0.0, max_value=3.0, value=0.70, step=0.05
    )
    terk_orani = (
        st.number_input(
            "Kamusal Terk Oranı (%)",
            min_value=0.0,
            max_value=100.0,
            value=30.0,
            step=1.0,
        )
        / 100.0
    )

if uploaded_files:
    results = []
    for pdf_file in uploaded_files:
        parsed_data = parse_imar_pdf_multi_zone(pdf_file)
        if parsed_data:
            results.append(parsed_data)

    if results:
        for data in results:
            with st.expander(
                f"📌 {data['dosya_adi']} - Ada: {data['ada']} / Parsel: {data['parsel']}",
                expanded=True,
            ):
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.text_input("Ada", value=data["ada"], disabled=True)
                col2.text_input("Parsel", value=data["parsel"], disabled=True)
                col3.number_input(
                    "Toplam Arazi m²",
                    value=float(data["m2"]),
                    format="%.2f",
                    disabled=True,
                )

                selected_kaks = (
                    custom_kaks if override_kaks else data["kaks"]
                )
                col4.number_input(
                    "Ağırlıklı KAKS",
                    value=float(selected_kaks),
                    format="%.2f",
                    disabled=True,
                )

                terk_tipi = col5.radio(
                    "Terk Durumu", ["Brüt", "Net"], key=f"terk_{data['dosya_adi']}"
                )

                st.write("**Tespit Edilen İmar Fonksiyonları Dağılımı**")
                if data["fonksiyonlar"]:
                    df_fonk = pd.DataFrame(data["fonksiyonlar"])
                    st.dataframe(df_fonk, use_container_width=True)

        st.subheader("📊 İmar Hesaplama Sonuçları")

        table_rows = []
        for data in results:
            gross_m2 = data["m2"]
            kaks_to_use = custom_kaks if override_kaks else data["kaks"]

            if terk_tipi == "Brüt":
                terk_m2 = gross_m2 * terk_orani
                net_m2 = gross_m2 - terk_m2
            else:
                net_m2 = gross_m2
                terk_m2 = 0.0

            emsal_insaat_m2 = net_m2 * kaks_to_use
            toplam_brut_insaat_m2 = emsal_insaat_m2 * 1.30
            zemin_oturumu_m2 = net_m2 * data["taks"]

            table_rows.append({
                "Ada/Parsel": f"{data['ada']}/{data['parsel']}",
                "Girdi m²": gross_m2,
                "Terk Durumu": terk_tipi,
                "Net m²": net_m2,
                "Terk m²": terk_m2,
                "TAKS": data["taks"],
                "Ağırlıklı KAKS": kaks_to_use,
                "Emsal İnşaat m²": emsal_insaat_m2,
                "Satılabilir Brut İnşaat m² (x1.3)": toplam_brut_insaat_m2,
                "Zemin Oturumu (TAKS) m²": zemin_oturumu_m2,
            })

        df_results = pd.DataFrame(table_rows)
        st.dataframe(df_results, use_container_width=True)

        st.write("**Özet Fizibilite Metrikleri**")
        summary_df = pd.DataFrame({
            "Metrik": [
                "Toplam Brüt Arazi m²",
                "Toplam Kamusal Terk m²",
                "Toplam Net Arazi m²",
                "Emsal İçi İnşaat m²",
                "Satılabilir Toplam Brüt İnşaat m² (x1.3)",
                "Zemin Oturumu (TAKS) m²",
            ],
            "Değer": [
                f"{df_results['Girdi m²'].sum():,.2f}",
                f"{df_results['Terk m²'].sum():,.2f}",
                f"{df_results['Net m²'].sum():,.2f}",
                f"{df_results['Emsal İnşaat m²'].sum():,.2f}",
                f"{df_results['Satılabilir Brut İnşaat m² (x1.3)'].sum():,.2f}",
                f"{df_results['Zemin Oturumu (TAKS) m²'].sum():,.2f}",
            ],
        })
        st.table(summary_df)
else:
    st.info("Lütfen sol panelden bir veya daha fazla İmar Raporu PDF'i yükleyin.")
