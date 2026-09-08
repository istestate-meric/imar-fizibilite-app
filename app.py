import io
import pandas as pd
import pdfplumber
import re
import streamlit as st

st.set_page_config(
    page_title="İmar & Toplu Fizibilite Analiz Portalı", layout="wide"
)


def parse_float_turk(val_str):
    if not val_str:
        return 0.0
    val_str = str(val_str).strip()
    # Harf ve m² gibi birimleri temizle
    val_str = re.sub(r"[^\d\.,]", "", val_str)
    if not val_str:
        return 0.0

    # 2,131.58 veya 2.131,58 veya 2131.58 dönüştürme
    if "," in val_str and "." in val_str:
        if val_str.find(",") < val_str.find("."):
            val_str = val_str.replace(",", "")  # 2,131.58 -> 2131.58
        else:
            val_str = val_str.replace(".", "").replace(
                ",", "."
            )  # 2.131,58 -> 2131.58
    elif "," in val_str:
        val_str = val_str.replace(",", ".")

    try:
        return float(val_str)
    except ValueError:
        return 0.0


def parse_imar_pdf_multi_zone(uploaded_file):
    full_text = ""
    tables_text = ""

    try:
        with pdfplumber.open(uploaded_file) as pdf:
            for page in pdf.pages:
                t = page.extract_text() or ""
                full_text += t + "\n"

                # Tabloları da string olarak topla
                tables = page.extract_tables()
                for tbl in tables:
                    for row in tbl:
                        if row:
                            tables_text += (
                                " ".join([str(c) for c in row if c]) + "\n"
                            )
    except Exception as e:
        st.error(f"PDF okuma hatası ({uploaded_file.name}): {e}")
        return None

    combined_text = full_text + "\n" + tables_text

    # --- 1. ADA & PARSEL YAKALAMA ---
    ada_val = "-"
    parsel_val = "-"

    ada_m = re.search(r"Ada[\s\n|:]*(\d+)", combined_text, re.I)
    parsel_m = re.search(r"Parsel[\s\n|:]*(\d+)", combined_text, re.I)

    if ada_m:
        ada_val = ada_m.group(1)
    if parsel_m:
        parsel_val = parsel_m.group(1)

    # Dosya adından fallback
    if ada_val == "-" or parsel_val == "-":
        fn_m = re.search(
            r"(\d+)\s*Ada\s*(\d+)\s*Parsel", uploaded_file.name, re.I
        )
        if fn_m:
            ada_val, parsel_val = fn_m.group(1), fn_m.group(2)

    # --- 2. BRÜT ARAZİ ALANI (m²) YAKALAMA ---
    m2_val = 0.0

    # Deneme A: "Alan *" / "Alan" etiketinin hemen yanındaki/altındaki m²
    area_patterns = [
        r"Alan\s*\*?[\s\n|:]*([\d\.,]+)\s*m²",
        r"Alan\s*\*?[\s\n|:]*([\d\.,]+)",
        r"([\d\.,]+)\s*m²[\s\n]*\*?\s*Grafik",
    ]

    for pat in area_patterns:
        m = re.search(pat, combined_text, re.I)
        if m:
            parsed = parse_float_turk(m.group(1))
            if parsed > 50:  # Makul bir arsa metrekaresi sınırı
                m2_val = parsed
                break

    # Deneme B: Eğer regex bulamadıysa, metin içerisindeki 'm²' geçen tüm sayıları tara
    if m2_val == 0.0:
        all_m2_matches = re.findall(r"([\d\.,]+)\s*m²", combined_text, re.I)
        candidates = []
        for match in all_m2_matches:
            val = parse_float_turk(match)
            if 50 <= val <= 500000:  # Tipik parsel metrekare aralığı
                candidates.append(val)
        if candidates:
            # Raporlarda en büyük m² genelde toplam tapu/grafik alanıdır
            m2_val = max(candidates)

    # --- 3. KAKS & TAKS YAKALAMA ---
    taks = 0.30
    taks_m = re.search(r"Taks[\s\n|:]*([\d\.,]+)", combined_text, re.I)
    if taks_m:
        v = parse_float_turk(taks_m.group(1))
        if 0.05 <= v <= 0.90:
            taks = v

    kaks = 0.30
    kaks_m = re.search(
        r"(?:Kaks|Emsal)\s*(?:\(Emsal\))?[\s\n|:]*([\d\.,]+)", combined_text, re.I
    )
    if kaks_m:
        v = parse_float_turk(kaks_m.group(1))
        if 0.05 <= v <= 3.0:
            kaks = v

    return {
        "dosya_adi": uploaded_file.name,
        "ada": ada_val,
        "parsel": parsel_val,
        "m2": m2_val,
        "taks": taks,
        "kaks": kaks,
    }


# --- ARAYÜZ & ÖNBELLEK ---
st.title("📌 İmar & Toplu Fizibilite Analiz Portalı")

if "parsed_results" not in st.session_state:
    st.session_state.parsed_results = []

with st.sidebar:
    st.header("📂 Toplu Belge Yükleme")
    uploaded_files = st.file_uploader(
        "İmar Raporu PDF'lerini Yükleyin (Çoklu Seçim)",
        type=["pdf"],
        accept_multiple_files=True,
    )

    if st.button("🔄 Dosyaları İşle"):
        if uploaded_files:
            results = []
            for pdf_file in uploaded_files:
                parsed_data = parse_imar_pdf_multi_zone(pdf_file)
                if parsed_data:
                    results.append(parsed_data)
            st.session_state.parsed_results = results

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

# --- TABLO VE HESAPLAMALAR ---
if st.session_state.parsed_results:
    table_rows = []
    for data in st.session_state.parsed_results:
        gross_m2 = data["m2"]
        kaks_to_use = custom_kaks if override_kaks else data["kaks"]

        terk_m2 = gross_m2 * terk_orani
        net_m2 = gross_m2 - terk_m2

        emsal_insaat_m2 = net_m2 * kaks_to_use
        toplam_brut_insaat_m2 = emsal_insaat_m2 * 1.30
        zemin_oturumu_m2 = net_m2 * data["taks"]

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

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df_results.to_excel(writer, sheet_name="Fizibilite Raporu", index=False)
    excel_data = output.getvalue()

    st.download_button(
        label="📥 Sonuçları Excel Olarak İndir",
        data=excel_data,
        file_name="imar_fizibilite_raporu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info(
        "Lütfen sol taraftan PDF belgelerinizi seçip 'Dosyaları İşle' butonuna basınız."
    )
    
