import io
import pandas as pd
import pdfplumber
import re
import streamlit as st

st.set_page_config(
    page_title="İmar & Toplu Fizibilite Analiz Portalı", layout="wide"
)


def clean_turkish_number(val_str):
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

    # --- 1. ADA & PARSEL YAKALAMA ---
    ada_val = "-"
    parsel_val = "-"

    # Tablo tabanlı arama
    for i, row in enumerate(tables_data):
        row_cells = [str(c).strip() for c in row if c is not None]
        row_str = " ".join(row_cells)

        if "Ada" in row_str and ada_val == "-":
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

    # Regex düşüşü
    if ada_val == "-" or parsel_val == "-":
        m = re.search(
            r"Ada[\s\n|:]*(\d+)[\s\n|]*Parsel[\s\n|:]*(\d+)", full_text, re.I
        )
        if m:
            ada_val, parsel_val = m.group(1), m.group(2)

    # --- 2. GERÇEK ANA PARSEL ALANI (m²) YAKALAMA ---
    m2_val = 0.0
    main_area_m = re.search(
        r"Alan\s*\*?[\s\n|:]*([\d\.,]+)\s*m²", full_text, re.I
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
        "m2": m2_val,
        "taks": round(agirlikli_taks, 2),
        "kaks": round(agirlikli_kaks, 2),
        "fonksiyonlar": fonksiyonlar,
    }


# --- ARAYÜZ ---
st.title("📌 İmar & Fizibilite Analiz Portalı")

with st.sidebar:
    st.header("📂 Toplu Belge Yükleme")
    uploaded_files = st.file_uploader(
        "İmar Raporu PDF'lerini Yükleyin (Çoklu Seçim)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    st.header("⚙️ İmar & Terk Parametreleri")
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

    st.header("💰 Finansal & Paylaşım Oranları")
    mutaahhit_payi = (
        st.number_input(
            "Müteahhit Payı (%)",
            min_value=0.0,
            max_value=100.0,
            value=50.0,
            step=5.0,
        )
        / 100.0
    )
    insaat_maliyeti_m2 = st.number_input(
        "İnşaat M² Maliyeti ($)", min_value=0, value=800, step=50
    )
    satis_fiyati_m2 = st.number_input(
        "Satış M² Fiyatı ($)", min_value=0, value=2500, step=100
    )

if uploaded_files:
    results = []
    for pdf_file in uploaded_files:
        parsed_data = parse_imar_pdf_multi_zone(pdf_file)
        if parsed_data:
            results.append(parsed_data)

    if results:
        table_rows = []
        for data in results:
            gross_m2 = data["m2"]
            kaks_to_use = custom_kaks if override_kaks else data["kaks"]

            terk_m2 = gross_m2 * terk_orani
            net_m2 = gross_m2 - terk_m2

            emsal_insaat_m2 = net_m2 * kaks_to_use
            toplam_brut_insaat_m2 = emsal_insaat_m2 * 1.30
            zemin_oturumu_m2 = net_m2 * data["taks"]

            # Finansal
            mutaahhit_brut_m2 = toplam_brut_insaat_m2 * mutaahhit_payi
            arsa_sahibi_brut_m2 = toplam_brut_insaat_m2 * (1 - mutaahhit_payi)
            toplam_maliyet = toplam_brut_insaat_m2 * insaat_maliyeti_m2
            mutaahhit_ciro = mutaahhit_brut_m2 * satis_fiyati_m2
            mutaahhit_kar = mutaahhit_ciro - toplam_maliyet

            table_rows.append({
                "Dosya": data["dosya_adi"],
                "Ada/Parsel": f"{data['ada']}/{data['parsel']}",
                "Girdi Brüt m²": gross_m2,
                "Net m²": net_m2,
                "Terk m²": terk_m2,
                "TAKS": data["taks"],
                "KAKS": kaks_to_use,
                "Emsal İnşaat m²": emsal_insaat_m2,
                "Satılabilir Toplam İnşaat m² (x1.3)": toplam_brut_insaat_m2,
                "Zemin Oturumu m²": zemin_oturumu_m2,
                "Müteahhit İnşaat m²": mutaahhit_brut_m2,
                "Arsa Sahibi İnşaat m²": arsa_sahibi_brut_m2,
                "Toplam İnşaat Maliyeti ($)": toplam_maliyet,
                "Müteahhit Ciro ($)": mutaahhit_ciro,
                "Müteahhit Tahmini Kar ($)": mutaahhit_kar,
            })

        df_results = pd.DataFrame(table_rows)

        st.subheader("📊 Toplu İmar ve Finansal Analiz Tablosu")
        st.dataframe(df_results, use_container_width=True)

        st.subheader("📈 Toplam Bölgesel Özet Fizibilite")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Toplam Brüt Arazi", f"{df_results['Girdi Brüt m²'].sum():,.2f} m²"
        )
        c2.metric(
            "Satılabilir Toplam İnşaat",
            f"{df_results['Satılabilir Toplam İnşaat m² (x1.3)'].sum():,.2f} m²",
        )
        c3.metric(
            "Toplam Maliyet",
            f"${df_results['Toplam İnşaat Maliyeti ($)'].sum():,.2f}",
        )
        c4.metric(
            "Müteahhit Toplam Kar",
            f"${df_results['Müteahhit Tahmini Kar ($)'].sum():,.2f}",
        )

        # Excel İndirme
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
            df_results.to_excel(
                writer, sheet_name="Fizibilite Raporu", index=False
            )
        excel_data = output.getvalue()

        st.download_button(
            label="📥 Sonuçları Excel Olarak İndir",
            data=excel_data,
            file_name="imar_fizibilite_raporu.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
else:
    st.info(
        "Lütfen sol taraftaki panelden analiz etmek istediğiniz PDF veya PDF grubunu yükleyin."
    )
