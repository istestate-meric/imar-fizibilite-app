import io
import re
import pandas as pd
import pdfplumber
import streamlit as st

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
    .card {background-color:#F8FAFC; padding:15px; border-radius:10px; border:1px solid #E2E8F0;}
    </style>
""",
    unsafe_allow_html=True,
)


# --- 1. OCR & PDF PARSER MODÜLÜ ---
def parse_imar_pdf(uploaded_file):
    """İmar Durumu PDF'inden temel verileri regex ile çeker."""
    text = ""
    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    # Alan ve Emsal Arama
    m2_match = re.search(
        r"(\d+[\.,]?\d*)\*?\s*(m2|m²|Metrekare)", text, re.IGNORECASE
    )
    kaks_match = re.search(
        r"(Emsal|KAKS)\s*:\s*(\d+[\.,]?\d*)", text, re.IGNORECASE
    )
    ada_match = re.search(r"Ada\s*:\s*(\d+)", text, re.IGNORECASE)
    parsel_match = re.search(r"Parsel\s*:\s*(\d+)", text, re.IGNORECASE)

    return {
        "dosya_adi": uploaded_file.name,
        "ada": ada_match.group(1) if ada_match else "-",
        "parsel": parsel_match.group(1) if parsel_match else "-",
        "m2": float(m2_match.group(1).replace(",", ".")) if m2_match else 0.0,
        "kaks": float(kaks_match.group(2).replace(",", "."))
        if kaks_match
        else 0.70,
        "ham_metin": text,
    }


# --- 2. HESAPLAMA MOTORU ---
def hesapla_tevhit_ve_fizibilite(parseller_listesi, finansal_parametreler):
    toplam_brut_arazi = 0
    toplam_net_arazi = 0
    toplam_terk = 0

    parsel_detaylari = []

    for p in parseller_listesi:
        m2 = p["m2"]
        terk_durumu = p["terk_durumu"]  # 'Brüt' veya 'Net'

        if terk_durumu == "Brüt":
            net = m2 * 0.70
            terk = m2 * 0.30
            brut = m2
        else:
            net = m2
            terk = 0.0
            brut = m2 / 0.70  # Tahmini brüt hesabı

        toplam_brut_arazi += brut
        toplam_net_arazi += net
        toplam_terk += terk

        parsel_detaylari.append({
            "Ada/Parsel": f"{p['ada']}/{p['parsel']}",
            "Girdi m²": m2,
            "Terk Durumu": terk_durumu,
            "Net m²": round(net, 2),
            "Terk m²": round(terk, 2),
            "KAKS": p["kaks"],
        })

    # Tevhit Alanı İmar Hakları (Ağırlıklı KAKS veya Sabit Seçilen KAKS)
    sabit_kaks = finansal_parametreler["kaks"]
    emsal_dahil_insaat = toplam_net_arazi * sabit_kaks
    toplam_brut_insaat = emsal_dahil_insaat * 1.30  # Plan Notu 1.3 Katsayısı
    taban_oturumu = (
        toplam_net_arazi * finansal_parametreler["taks"]
    )  # TAKS Hesabı

    birim_konut_m2 = finansal_parametreler["birim_konut_m2"]
    tahmini_unite_sayisi = int(toplam_brut_insaat // birim_konut_m2)

    # FINANSAL SENARYOLAR
    m2_maliyet = finansal_parametreler["m2_maliyet"]
    m2_satis = finansal_parametreler["m2_satis"]

    toplam_proje_maliyeti = toplam_brut_insaat * m2_maliyet
    toplam_proje_hasilati = toplam_brut_insaat * m2_satis

    # Senaryo 1: Öz Sermaye (Kendi Yapımı)
    ozsermaye_kar = toplam_proje_hasilati - toplam_proje_maliyeti
    ozsermaye_roi = (
        (ozsermaye_kar / toplam_proje_maliyeti * 100)
        if toplam_proje_maliyeti > 0
        else 0
    )

    # Senaryo 2: Kat Karşılığı (% Kat Karşılığı Oranı)
    kat_orani_mutaahhit = finansal_parametreler["kat_kar_mutaahhit_payi"] / 100
    mutaahhit_insaat_payi = toplam_brut_insaat * kat_orani_mutaahhit
    mutaahhit_hasilati = mutaahhit_insaat_payi * m2_satis
    mutaahhit_kat_kari = mutaahhit_hasilati - toplam_proje_maliyeti
    arsa_sahibi_unite = int(
        (toplam_brut_insaat * (1 - kat_orani_mutaahhit)) // birim_konut_m2
    )

    # Senaryo 3: Hasılat Paylaşımı (% Paylaşım Oranı)
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
            "Emsal (KAKS)": sabit_kaks,
            "Emsal İçi İnşaat m²": round(emsal_dahil_insaat, 2),
            "Satılabilir Toplam Brüt İnşaat m² (x1.3)": round(
                toplam_brut_insaat, 2
            ),
            "Zemin Oturumu (TAKS) m²": round(taban_oturumu, 2),
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


# --- 3. KULLANICI ARAYÜZÜ (STREAMLIT) ---
st.markdown(
    '<div class="main-header">🏢 Gayrimenkul İmar, Tevhit & Fizibilite Paneli</div>',
    unsafe_allow_html=True,
)

# SIDEBAR: DOSYA YÜKLEME & PARAMETRELER
st.sidebar.header("📁 1. Belge Yükleme (PDF)")
uploaded_files = st.sidebar.file_uploader(
    "İmar Raporu PDF'lerini Yükleyin (Çoklu)",
    type=["pdf"],
    accept_multiple_files=True,
)

st.sidebar.header("⚙️ 2. İmar & Finansal Parametreler")
kaks_input = st.sidebar.number_input("Birleşik KAKS (Emsal)", value=0.70, step=0.05)
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

# PARSEL BİLGİLERİ YÖNETİMİ
parsel_listesi = []

if uploaded_files:
    st.info(f"📂 {len(uploaded_files)} Adet PDF Yüklendi. Veriler Ayrıştırılıyor...")
    for idx, f in enumerate(uploaded_files):
        parsed = parse_imar_pdf(f)
        col1, col2, col3, col4 = st.columns([2, 2, 2, 3])
        ada = col1.text_input(
            f"Ada ({f.name[:10]}...)", value=parsed["ada"], key=f"ada_{idx}"
        )
        parsel = col2.text_input(f"Parsel", value=parsed["parsel"], key=f"parsel_{idx}")
        m2 = col3.number_input(f"m²", value=parsed["m2"], key=f"m2_{idx}")
        terk_durumu = col4.radio(
            f"Terk Durumu",
            ("Brüt", "Net"),
            key=f"terk_{idx}",
            horizontal=True,
        )

        parsel_listesi.append({
            "ada": ada,
            "parsel": parsel,
            "m2": m2,
            "kaks": parsed["kaks"],
            "terk_durumu": terk_durumu,
        })
else:
    st.warning(
        "⚠️ PDF Yüklemediniz. Manuel Parsel Girişi Yapabilirsiniz (Örnek Parsel Eklendi):"
    )
    col1, col2, col3, col4 = st.columns([2, 2, 2, 3])
    ada = col1.text_input("Ada", value="1437")
    parsel = col2.text_input("Parsel", value="17")
    m2 = col3.number_input("Arazi m²", value=1000.0)
    terk_durumu = col4.radio(
        "Terk Durumu", ("Brüt", "Net"), index=0, horizontal=True
    )

    parsel_listesi.append({
        "ada": ada,
        "parsel": parsel,
        "m2": m2,
        "kaks": kaks_input,
        "terk_durumu": terk_durumu,
    })

# HESAPLAMALARI ÇALIŞTIR
finansal_params = {
    "kaks": kaks_input,
    "taks": taks_input,
    "birim_konut_m2": birim_konut_m2,
    "m2_maliyet": m2_maliyet,
    "m2_satis": m2_satis,
    "kat_kar_mutaahhit_payi": kat_mutaahhit_payi,
    "hasilat_arsa_payi": hasilat_arsa_payi,
}

sonuclar = hesapla_tevhit_ve_fizibilite(parsel_listesi, finansal_params)

# --- SONUÇLARIN GÖSTERİMİ ---
st.markdown("---")
st.markdown(
    '<div class="sub-header">📊 1. Parsel & Tevhit İmar Özeti</div>',
    unsafe_allow_html=True,
)

col_left, col_right = st.columns([1, 1])

with col_left:
    st.write("**Parsel Kırılımları**")
    st.dataframe(sonuclar["parsel_detaylari"], use_container_width=True)

with col_right:
    st.write("**Tevhit Sonrası Birleşik İmar Hakları**")
    df_imar = pd.DataFrame(
        list(sonuclar["ozet_imar"].items()), columns=["Metrik", "Değer"]
    )
    st.table(df_imar)

st.markdown("---")
st.markdown(
    '<div class="sub-header">💰 2. 3 Farklı Finansal Fizibilite Senaryosu</div>',
    unsafe_allow_html=True,
)

f1, f2, f3 = st.columns(3)

with f1:
    st.markdown("### 1. Öz Sermaye (Kendi Yapımı)")
    for k, v in sonuclar["finansal_senaryolar"]["Senaryo 1: Öz Sermaye"].items():
        st.metric(k, v)

with f2:
    st.markdown("### 2. Kat Karşılığı Modeli")
    for k, v in sonuclar["finansal_senaryolar"][
        "Senaryo 2: Kat Karşılığı"
    ].items():
        st.metric(k, v)

with f3:
    st.markdown("### 3. Hasılat Paylaşımı Modeli")
    for k, v in sonuclar["finansal_senaryolar"][
        "Senaryo 3: Hasılat Paylaşımı"
    ].items():
        st.metric(k, v)

# EXCEL EXPORT
st.markdown("---")
buffer = io.BytesIO()
with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
    sonuclar["parsel_detaylari"].to_excel(
        writer, sheet_name="Parseller", index=False
    )
    df_imar.to_excel(writer, sheet_name="İmar Özet", index=False)

st.download_button(
    label="📥 Konsolide Excel Fizibilite Raporunu İndir",
    data=buffer.getvalue(),
    file_name="Konsolide_Imar_Fizibilite_Raporu.xlsx",
    mime="application/vnd.ms-excel",
)
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_pdf_katalog(sonuclar, proje_adi="İmar & Fizibilite Analizi"):
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

    # Özel Stiller
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1E3A8A'),
        alignment=1,
        spaceAfter=20,
    )
    subtitle_style = ParagraphStyle(
        'SubTitleStyle',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#3B82F6'),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        'BodyStyle', parent=styles['Normal'], fontSize=10, textColor=colors.navy
    )

    # 1. KAPAK SAYFASI
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("GAYRİMENKUL DEĞERLEME &", title_style))
    elements.append(
        Paragraph("İMAR FİZİBİLİTE SUNUM KATALOĞU", title_style)[cite: 4]
    )
    elements.append(
        HRFlowable(
            width="100%",
            thickness=3,
            color=colors.HexColor("#1E3A8A"),
            spaceAfter=30,
        )
    )
    elements.append(
        Paragraph(f"<b>Proje / Bölge:</b> {proje_adi}", body_style)[cite: 4]
    )
    elements.append(Spacer(1, 150))

    # Özet Kutu
    ozet_data = [
        [
            "Net Arazi m²",
            f"{sonuclar['ozet_imar']['Toplam Net Arazi m²']} m²",
        ],
        [
            "Toplam Brüt İnşaat m² (x1.3)",
            f"{sonuclar['ozet_imar']['Satılabilir Toplam Brüt İnşaat m² (x1.3)']} m²",
        ],
        [
            "Tahmini Konut Adedi",
            f"{sonuclar['ozet_imar']['Tahmini Ünite / Konut Adedi']} Adet",
        ],
    ]
    t_ozet = Table(ozet_data, colWidths=[200, 250])
    t_ozet.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#E2E8F0')),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('PADDING', (0, 0), (-1, -1), 10),
        ])
    )
    elements.append(t_ozet)
    elements.append(PageBreak())

    # 2. İMAR VE PARSEL BİLGİLERİ
    elements.append(
        Paragraph("1. PARSEL VE İMAR DURUMU ANALİZİ", subtitle_style)
    )
    elements.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#3B82F6"),
            spaceAfter=15,
        )
    )

    imar_table_data = [["Metrik", "Değer"]] + [
        [k, str(v)] for k, v in sonuclar["ozet_imar"].items()
    ]
    t_imar = Table(imar_table_data, colWidths=[250, 200])
    t_imar.setStyle(
        TableStyle([
            ('BACKGROUND', (0, 0), (1, 0), colors.HexColor('#1E3A8A')),
            ('TEXTCOLOR', (0, 0), (1, 0), colors.white),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ])
    )
    elements.append(t_imar)
    elements.append(Spacer(1, 20))

    # 3. FİNANSAL FİZİBİLİTE SENARYOLARI
    elements.append(
        Paragraph("2. FİNANSAL FİZİBİLİTE & MODEL SENARYOLARI", subtitle_style)[
            cite: 2
        ]
    )
    elements.append(
        HRFlowable(
            width="100%",
            thickness=1,
            color=colors.HexColor("#3B82F6"),
            spaceAfter=15,
        )
    )

    for senaryo_adi, detaylar in sonuclar["finansal_senaryolar"].items():
        elements.append(
            Paragraph(f"<b>{senaryo_adi}</b>", styles["Heading3"])
        )
        s_data = [[k, str(v)] for k, v in detaylar.items()]
        t_s = Table(s_data, colWidths=[250, 200])
        t_s.setStyle(
            TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F1F5F9')),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94A3B8')),
                ('PADDING', (0, 0), (-1, -1), 5),
            ])
        )
        elements.append(t_s)
        elements.append(Spacer(1, 10))

    doc.build(elements)
    buffer.seek(0)
    return buffer
