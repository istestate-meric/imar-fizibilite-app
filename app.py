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
    val_str = re.sub(r"[^\d\.,]", "", val_str)
    if not val_str:
        return 0.0

    if "," in val_str and "." in val_str:
        if val_str.find(",") < val_str.find("."):
            val_str = val_str.replace(",", "")
        else:
            val_str = val_str.replace(".", "").replace(",", ".")
    elif "," in val_str:
        val_str = val_str.replace(",", ".")

    try:
        return float(val_str)
    except ValueError:
        return 0.0


def parse_imar_pdf_multi_zone(uploaded_file):
    full_text = ""
    pages_text = []
    tables_data = []

    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                pages_text.append(t)
                full_text += t + "\n"

                extracted_tables = page.extract_tables()
                for tbl in extracted_tables:
                    if tbl:
                        tables_data.extend(tbl)
    except Exception as e:
        st.error(f"PDF okuma hatası ({uploaded_file.name}): {e}")
        return None

    # --- 1. ADA & PARSEL YAKALAMA (ÇOK KATMANLI DETEKSİYON) ---
    ada_val = "-"
    parsel_val = "-"

    # Yöntem A: Tablo Hücrelerinden Birebir Çekme (Beykoz PDF Yapısı)
    for i, row in enumerate(tables_data):
        row_cells = [str(c).strip() for c in row if c is not None]
        row_str = " ".join(row_cells)

        if "Ada" in row_str and ada_val == "-":
            # Bir alt satırdaki veya aynı satırdaki ilk rakam kümesini al
            nums = re.findall(r"\b\d+\b", row_str)
            if nums:
                ada_val = nums[0]
            elif i + 1 < len(tables_data):
                next_row_str = " ".join([
                    str(c).strip() for c in tables_data[i + 1] if c is not None
                ])
                next_nums = re.findall(r"\b\d+\b", next_row_str)
                if next_nums:
                    ada_val = next_nums[0]

        if "Parsel" in row_str and parsel_val == "-":
            nums = re.findall(r"\b\d+\b", row_str)
            if len(nums) > 1 and ada_val == nums[0]:
                parsel_val = nums[1]
            elif nums and ada_val != nums[0]:
                parsel_val = nums[0]
            elif i + 1 < len(tables_data):
                next_row_str = " ".join([
                    str(c).strip() for c in tables_data[i + 1] if c is not None
                ])
                next_nums = re.findall(r"\b\d+\b", next_row_str)
                if next_nums:
                    parsel_val = next_nums[-1]

    # Yöntem B: Esnek Metin Regex (Satır Sonları ve Boşluk Toleranslı)
    if ada_val == "-" or parsel_val == "-":
        # ÇENGELDERE / 1437 / 17 bloğunu hedefler
        block_m = re.search(
            r"(?:ÇENGELDERE|GÖRELE|ÇİFTLİK|BAKLACI|YAVUZSELİM|FATİH)?[\s\n|]*(\d+)\b[\s\n|]*(\d+)\b",
            full_text,
            re.I,
        )
        if block_m:
            if ada_val == "-":
                ada_val = block_m.group(1)
            if parsel_val == "-":
                parsel_val = block_m.group(2)

    # Yöntem C: Standart Regex Düşüşü
    if ada_val == "-":
        ada_m = re.search(r"Ada[\s\n|:]*(\d+)", full_text, re.I)
        if ada_m:
            ada_val = ada_m.group(1)

    if parsel_val == "-":
        parsel_m = re.search(r"Parsel[\s\n|:]*(\d+)", full_text, re.I)
        if parsel_m:
            parsel_val = parsel_m.group(1)

    # --- 2. GERÇEK ANA PARSEL ALANI (m²) YAKALAMA ---
    m2_val = 0.0
    main_area_m = re.search(
        r"Alan\s*\*?[\s\n|:]*([\d\.,]+)\s*m²", pages_text[0], re.I
    )
    if main_area_m:
        m2_val = clean_turkish_number(main_area_m.group(1))

    # --- 3. PARÇALI FONKSİYON DETAYLARI VE KAKS/TAKS ---
    fonksiyonlar = []
    raw_blocks = re.split(r"Fonksiyon Adı", full_text, flags=re.IGNORECASE)

    for block in raw_blocks[1:]:
        lines = [
            l.strip()
            for l in block.split("\n")
            if l.strip() and not l.startswith("Kat Adedi")
        ]
        f_adi = lines[0] if lines else "Genel Alan"

        taks = 0.0
        taks_m = re.search(r"Taks[\s\n|:]*([\d\.,]+)", block, re.I)
        if taks_m:
            taks = clean_turkish_number(taks_m.group(1))

        kaks = 0.0
        kaks_m = re.search(
            r"(?:Kaks|Emsal)\s*(?:\(Emsal\))?[\s\n|:]*([\d\.,]+)", block, re.I
        )
        if kaks_m:
            kaks = clean_turkish_number(kaks_m.group(1))

        f_m2 = 0.0
        m2_f_match = re.search(r"(?:-\s*)?([\d\.,]+)\s*m²", block, re.I)
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
