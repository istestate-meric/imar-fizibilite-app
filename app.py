import io
import re
import pandas as pd
import pdfplumber
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# --- SAYFA AYARLARI ---
st.set_page_config(
    page_title="İmar & Fizibilite Master Dashboard",
    page_icon="🏢",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- TASARIM & CSS ---
st.markdown(
    """
    <style>
    .main-header {font-size:26px; font-weight:bold; color:#1E3A8A; margin-bottom:10px;}
    .sub-header {font-size:18px; font-weight:600; color:#3B82F6;}
    </style>
""",
    unsafe_allow_html=True,
)


# --- 1. BELEDİYE UYUMLU PDF PARSER ---
def parse_imar_pdf(uploaded_file):
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    # Ada & Parsel
    ada_val = "-"
    parsel_val = "-"

    ada_match = re.search(
        r"Ada\s*[:\s|]+(\d+)|Ada\s*\n\s*(\d+)", text, re.IGNORECASE
    )
    if ada_match:
        ada_val = ada_match.group(1) or ada_match.group(2)

    parsel_match = re.search(
        r"Parsel\s*[:\s|]+(\d+)|Parsel\s*\n\s*(\d+)", text, re.IGNORECASE
    )
    if parsel_match:
        parsel_val = parsel_match.group(1) or parsel_match.group(2)

    if ada_val == "-" or parsel_val == "-":
        ada_parsel_pattern = re.search(r"(\d{3,5})\s*[\s|]\s*(\d{1,4})", text)
        if ada_parsel_pattern:
            if ada_val == "-":
                ada_val = ada_parsel_pattern.group(1)
            if parsel_val == "-":
                parsel_val = ada_parsel_pattern.group(2)

    if ada_val == "-" or parsel_val == "-":
        filename_match = re.search(
            r"(\d+)\s*Ada\s*(\d+)\s*Parsel", uploaded_file.name, re.IGNORECASE
        )
        if filename_match:
            ada_val = filename_match.group(1)
            parsel_val = filename_match.group(2)

    # Arazi m²
    m2_val = 0.0
    m2_match = re.search(
        r"([\d\.,]+)\s*(m2|m²|Metrekare)", text, re.IGNORECASE
    )
    if m2_match:
        raw_m2 = m2_match.group(1).strip()
        if "," in raw_m2 and "." in raw_m2:
            if raw_m2.find(",") < raw_m2.find("."):
                raw_m2 = raw_m2.replace(",", "")
            else:
                raw_m2 = raw_m2.replace(".", "").replace(",", ".")
        elif "," in raw_m2:
            raw_m2 = raw_m2.replace(",", ".")
        try:
            m2_val = float(raw_m2)
        except ValueError:
            m2_val = 0.0

    # TAKS & KAKS (Emsal)
    taks_val = 0.30
    kaks_val = 0.30

    taks_match = re.search(
        r"Taks\s*[:\s|\n]*\s*(\d+[\.,]\d+)", text, re.IGNORECASE
    )
    if taks_match:
        try:
            taks_val = float(taks_match.group(1).replace(",", "."))
        except ValueError:
            taks_val = 0.30

    kaks_match = re.search(
        r"(Kaks|Emsal)\s*(\(Emsal\))?\s*[:\s|\n]*\s*(\d+[\.,]\d+)",
        text,
        re.IGNORECASE,
    )
    if kaks_match:
        try:
            kaks_val = float(kaks_match.group(3).replace(",", "."))
        except ValueError:
            kaks_val = 0.30

    return {
        "dosya_adi": uploaded_file.name,
        "ada": ada_val,
        "parsel": parsel_val,
        "m2": m2_val,
        "taks": taks_val,
        "kaks": kaks_val,
    }


# --- 2. DÜZELTİLMİŞ HESAPLAMA MOTORU ---
def hesapla_tevhit_ve_fizibilite(parseller_listesi, finansal_parametreler):
    toplam_brut_arazi = 0
    toplam_net_arazi = 0
    toplam_terk = 0
    toplam_emsal_insaat = 0.0
    toplam_zemin_oturumu = 0.0
    parsel_detaylari = []

    sabit_kaks_override = finansal_parametreler["sabit_kaks_override"]
    sabit_kaks = finansal_parametreler["sabit_kaks"]

    for p in parseller_listesi:
        m2 = p["m2"]
        terk_durumu = p["terk_durumu"]

        if terk_durumu == "Brüt":
            net = m2 * 0.70
            terk = m2 * 0.30
            brut = m2
        else:
            net = m2
            terk = 0.0
            brut = m2 / 0.70

        # Eğer sol menüdeki override seçili değilse parselin kendi KAKS/TAKS'ı kullanılır
        kaks = (
            sabit_kaks
            if (sabit_kaks_override and sabit_kaks > 0)
            else p["kaks"]
        )
        taks = p["taks"]

        parsel_emsal_m2 = net * kaks
        parsel_zemin_m2 = net * taks

        toplam_brut_arazi += brut
        toplam_net_arazi += net
        toplam_terk += terk
        toplam_emsal_insaat += parsel_emsal_m2
        toplam_zemin_oturumu += parsel_zemin_m2

        parsel_detaylari.append({
            "Ada/Parsel": f"{p['ada']}/{p['parsel']}",
            "Girdi m²": m2,
            "Terk Durumu": terk_durumu,
            "Net m²": round(net, 2),
            "Terk m²": round(terk, 2),
            "TAKS": taks,
            "KAKS": kaks,
            "Emsal İnşaat m²": round(parsel_emsal_m2, 2),
        })

    # Toplam Satılabilir Brüt İnşaat (Emsal Dışı %30 Katı)
    toplam_brut_insaat = toplam_emsal_insaat * 1.30

    # Ağırlıklı Ortalama KAKS gösterimi
    ort_kaks = (
        round(toplam_emsal_insaat / toplam_net_arazi, 4)
        if toplam_net_arazi > 0
        else 0
    )

    birim_konut_m2 = finansal_parametreler["birim_konut_m2"]
    tahmini_unite_sayisi = int(toplam_brut_insaat // birim_konut_m2)

    m2_maliyet = finansal_parametreler["m2_maliyet"]
    m2_satis = finansal_parametreler["m2_satis"]

    toplam_proje_maliyeti = toplam_brut_insaat * m2_maliyet
    toplam_proje_hasilati = toplam_brut_insaat * m2_satis

    # Finansal Senaryolar
    ozsermaye_kar = toplam_proje_hasilati - toplam_proje_maliyeti
    ozsermaye_roi = (
        (ozsermaye_kar / toplam_proje_maliyeti * 100)
        if toplam_proje_maliyeti > 0
        else 0
    )

    kat_orani_mutaahhit = finansal_parametreler["kat_kar_mutaahhit_payi"] / 100
    mutaahhit_insaat_payi = toplam_brut_insaat * kat_orani_mutaahhit
    mutaahhit_hasilati = mutaahhit_insaat_payi * m2_satis
    mutaahhit_kat_kari = mutaahhit_hasilati - toplam_proje_maliyeti
    arsa_sahibi_unite = int(
        (toplam_brut_insaat * (1 - kat_orani_mutaahhit)) // birim_konut_m2
    )

    hasilat_orani_arsa = finansal_parametreler["hasilat_arsa_payi"] / 100
    arsa_sahibi_hasilat = toplam_proje_hasilati * hasilat_orani_arsa
    mutaahhit_hasilat_payi = toplam_proje_hasilati * (1 - hasilat_orani_arsa)
    mutaahhit_hasilat_kari = mutaahhit_hasilat_payi - toplam_proje_maliyeti

    return {
        "parsel_detaylari": pd.DataFrame(parsel_detaylari),
        "ozet_imar": {
            "Toplam Brüt Arazi m²": round(toplam_brut_arazi, 2),
            "Toplam Kamusal Terk m²": round(toplam_terk, 2),
            "Toplam Net Arazi m²": round(toplam_net_arazi, 2),
            "Emsal (Ortalama KAKS)": ort_kaks,
            "Emsal İçi İnşaat m²": round(toplam_emsal_insaat, 2),
            "Satılabilir Toplam Brüt İnşaat m² (x1.3)": round(
                toplam_brut_insaat, 2
            ),
            "Zemin Oturumu (TAKS) m²": round(toplam_zemin_oturumu, 2),
            "Tahmini Ünite / Konut Adedi": tahmini_unite_sayisi,
        },
        "finansal_senaryolar": {
            "Senaryo 1: Öz Sermaye": {
                "Toplam Maliyet": f"{toplam_proje_maliyeti:,.0f} TL",
                "Toplam Hasılat": f"{toplam_proje_hasilati:,.0f} TL",
                "Net Kâr": f"{ozsermaye_kar:,.0f} TL",
                "Kâr Marjı (ROI)": f"%{ozsermaye_roi:.2f}",
            },
            "Senaryo 2: Kat Karşılığı": {
                "Müteahhit Payı (%)": f"%{finansal_parametreler['kat_kar_mutaahhit_payi']}",
                "Müteahhit Brüt İnşaat m²": round(mutaahhit_insaat_payi, 2),
                "Arsa Sahibi Ünite Hakedişi": f"{arsa_sahibi_unite} Adet",
                "Müteahhit Net Kârı": f"{mutaahhit_kat_kari:,.0f} TL",
            },
            "Senaryo 3: Hasılat Paylaşımı": {
                "Arsa Sahibi Payı (%)": f"%{finansal_parametreler['hasilat_arsa_payi']}",
                "Arsa Sahibi Geliri": f"{arsa_sahibi_hasilat:,.0f} TL",
                "Müteahhit Geliri": f"{mutaahhit_hasilat_payi:,.0f} TL",
                "Müteahhit Net Kârı": f"{mutaahhit_hasilat_kari:,.0f} TL",
            },
        },
    }


# --- 3. KURUMSAL PDF KATALOĞU ---
def generate_pdf_katalog(sonuclar):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )
    elements = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=20,
        textColor=colors.HexColor('#1E3A8A'),
        alignment=1,
        spaceAfter=15,
    )
    subtitle_style = ParagraphStyle(
        'SubTitleStyle',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#3B82F6'),
        spaceBefore=12,
        spaceAfter=6,
    )

    elements.append(
        Paragraph("GAYRİMENKUL İMAR & FİZİBİLİTE KATALOĞU", title_style)
    )
    elements.append(
        HRFlowable(
            width="100%",
            thickness=2,
            color=colors.HexColor("#1E3A8A"),
            spaceAfter=15,
        )
    )

    elements.append(Paragraph("1. İMAR DURUMU AÇIKLAMASI", subtitle_style))
    imar_table_data = [["Metrik", "Değer"]] + [
        [k, str(v)] for k, v in sonuclar["ozet_imar"].items()
    ]
    t_imar = Table(imar_table_data, colWidths=[250, 200])
    t_imar.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 5),
        ])
    )
    elements.append(t_imar)

    doc.build(elements)
    buffer.seek(0)
    return buffer


# --- 4. STREAMLIT ARAYÜZÜ ---
st.markdown(
    '<div class="main-header">🏢 Gayrimenkul İmar, Tevhit & Fizibilite Paneli</div>',
    unsafe_allow_html=True,
)

st.sidebar.header("📁 1. Belge Yükleme (PDF)")
uploaded_files = st.sidebar.file_uploader(
    "İmar Raporu PDF'lerini Yükleyin (Çoklu)",
    type=["pdf"],
    accept_multiple_files=True,
)

st.sidebar.header("⚙️ 2. İmar & Finansal Parametreler")
override_kaks = st.sidebar.checkbox(
    "Tevhit/Özel KAKS Kullan (PDF'leri Ez)", value=False
)
kaks_input = st.sidebar.number_input(
    "Birleşik KAKS (Emsal)", value=0.70, step=0.05, disabled=not override_kaks
)
taks_input = st.sidebar.number_input("TAKS (Zemin Oturumu)", value=0.30, step=0.05)
birim_konut_m2 = st.sidebar.number_input("Birim Konut Brüt m²", value=200)

st.sidebar.subheader("Maliyet & Satış Rayiçleri")
m2_maliyet = st.sidebar.number_input(
    "m² İnşaat Maliyeti (TL)", value=30000, step=1000
)
m2_satis = st.sidebar.number_input(
    "m² Satış Rayici (TL)", value=90000, step=2500
)

st.sidebar.subheader("Model Paylaşım Oranları")
kat_mutaahhit_payi = st.sidebar.slider("Kat Karşılığı Müteahhit Payı (%)", 30, 70, 50)
hasilat_arsa_payi = st.sidebar.slider("Hasılat Paylaşımı Arsa Payı (%)", 30, 70, 45)

parsel_listesi = []

if uploaded_files:
    st.info(f"📂 {len(uploaded_files)} Adet PDF Yüklendi.")
    for idx, f in enumerate(uploaded_files):
        parsed = parse_imar_pdf(f)
        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
        ada = col1.text_input(
            f"Ada ({f.name[:8]}...)", value=parsed["ada"], key=f"ada_{idx}"
        )
        parsel = col2.text_input(f"Parsel", value=parsed["parsel"], key=f"parsel_{idx}")
        m2 = col3.number_input(f"m²", value=parsed["m2"], key=f"m2_{idx}")
        kaks_val = col4.number_input(
            f"KAKS", value=parsed["kaks"], key=f"kaks_{idx}", step=0.05
        )
        terk_durumu = col5.radio(
            f"Terk", ("Brüt", "Net"), key=f"terk_{idx}", horizontal=True
        )

        parsel_listesi.append({
            "ada": ada,
            "parsel": parsel,
            "m2": m2,
            "taks": parsed["taks"],
            "kaks": kaks_val,
            "terk_durumu": terk_durumu,
        })

finansal_params = {
    "sabit_kaks_override": override_kaks,
    "sabit_kaks": kaks_input,
    "taks": taks_input,
    "birim_konut_m2": birim_konut_m2,
    "m2_maliyet": m2_maliyet,
    "m2_satis": m2_satis,
    "kat_kar_mutaahhit_payi": kat_mutaahhit_payi,
    "hasilat_arsa_payi": hasilat_arsa_payi,
}

if parsel_listesi:
    sonuclar = hesapla_tevhit_ve_fizibilite(parsel_listesi, finansal_params)

    st.markdown("---")
    st.markdown(
        '<div class="sub-header">📊 1. Parsel & Tevhit İmar Özeti</div>',
        unsafe_allow_html=True,
    )

    col_left, col_right = st.columns([1.2, 1])
    with col_left:
        st.dataframe(sonuclar["parsel_detaylari"], use_container_width=True)

    with col_right:
        df_imar = pd.DataFrame(
            list(sonuclar["ozet_imar"].items()), columns=["Metrik", "Değer"]
        )
        st.table(df_imar)

    st.markdown("---")
    st.markdown(
        '<div class="sub-header">💰 2. Finansal Fizibilite Senaryoları</div>',
        unsafe_allow_html=True,
    )

    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("### Öz Sermaye")
        for k, v in sonuclar["finansal_senaryolar"][
            "Senaryo 1: Öz Sermaye"
        ].items():
            st.metric(k, v)

    with f2:
        st.markdown("### Kat Karşılığı")
        for k, v in sonuclar["finansal_senaryolar"][
            "Senaryo 2: Kat Karşılığı"
        ].items():
            st.metric(k, v)

    with f3:
        st.markdown("### Hasılat Paylaşımı")
        for k, v in sonuclar["finansal_senaryolar"][
            "Senaryo 3: Hasılat Paylaşımı"
        ].items():
            st.metric(k, v)

    # İNDİRME BUTONLARI
    st.markdown("---")
    col_btn1, col_btn2 = st.columns(2)

    buffer_excel = io.BytesIO()
    with pd.ExcelWriter(buffer_excel, engine="xlsxwriter") as writer:
        sonuclar["parsel_detaylari"].to_excel(
            writer, sheet_name="Parseller", index=False
        )
        df_imar.to_excel(writer, sheet_name="İmar Özet", index=False)

    col_btn1.download_button(
        label="📥 Excel Fizibilite Raporu İndir",
        data=buffer_excel.getvalue(),
        file_name="Imar_Fizibilite_Raporu.xlsx",
        mime="application/vnd.ms-excel",
        use_container_width=True,
    )

    pdf_buffer = generate_pdf_katalog(sonuclar)
    col_btn2.download_button(
        label="📄 Kurumsal PDF Kataloğunu İndir",
        data=pdf_buffer,
        file_name="Imar_Fizibilite_Sunumu.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
