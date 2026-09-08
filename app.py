import io
import json
import re
import pandas as pd
import streamlit as st
import pdfplumber
import google.generativeai as genai
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Sayfa Yapılandırması
st.set_page_config(page_title="İstestate Meriç - İmar & Fizibilite Portalı", layout="wide")

# API Key Secrets kontrolü
try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    gemini_api_key = None

# Türkçe Karakter Düzeltici (PDF Çıktısı İçin)
def tr_fix(text):
    if not isinstance(text, str):
        return text
    replacements = {
        'ı': 'i', 'İ': 'I', 'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U', 'ş': 's', 'Ş': 'S',
        'ö': 'o', 'Ö': 'O', 'ç': 'c', 'Ç': 'C'
    }
    for search, replace in replacements.items():
        text = text.replace(search, replace)
    return text

# Session State Başlangıç Değerleri
if "mahalle" not in st.session_state:
    st.session_state.mahalle = "Yavuzselim"
if "ada" not in st.session_state:
    st.session_state.ada = "1658"
if "parsel" not in st.session_state:
    st.session_state.parsel = "1"
if "tapu_alani" not in st.session_state:
    st.session_state.tapu_alani = 6721.92
if "kaks" not in st.session_state:
    st.session_state.kaks = 0.40
if "taks" not in st.session_state:
    st.session_state.taks = 0.30

# Header Logoları
col_l1, col_l2 = st.columns([1, 4])
with col_l1:
    try:
        st.image("istestate_logo.png", width=180)
    except Exception:
        pass
with col_l2:
    st.title("İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK & MERİÇ İNŞAAT EMLAK")
    st.subheader("Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli")

st.divider()

# Sol Panel
with st.sidebar:
    st.header("1. Belge ile Otomatik Analiz")
    uploaded_pdf = st.file_uploader("İmar Durumu PDF Raporu Yükleyin", type=["pdf"])

    if not gemini_api_key:
        gemini_api_key = st.text_input("Gemini API Key", type="password")

    if uploaded_pdf is not None and gemini_api_key:
        if st.button("PDF Verilerini Forma Aktar"):
            with st.spinner("PDF Analiz Ediliyor..."):
                try:
                    with pdfplumber.open(uploaded_pdf) as pdf:
                        extracted_text = "\n".join([page.extract_text() or "" for page in pdf.pages])

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
                        st.session_state.mahalle = str(data.get("mahalle", st.session_state.mahalle))
                        st.session_state.ada = str(data.get("ada", st.session_state.ada))
                        st.session_state.parsel = str(data.get("parsel", st.session_state.parsel))
                        st.session_state.tapu_alani = float(data.get("tapu_alani", st.session_state.tapu_alani))
                        st.session_state.kaks = float(data.get("kaks", st.session_state.kaks))
                        st.session_state.taks = float(data.get("taks", st.session_state.taks))
                        st.success("Bilgiler PDF'ten başarıyla aktarıldı!")
                        st.rerun()
                except Exception as e:
                    st.error(f"Hata Oluştu: {e}")

    st.header("2. Parsel & Bölge İmar Fonksiyonu")
    mahalle = st.text_input("Mahalle", value=st.session_state.mahalle)
    ada = st.text_input("Ada No", value=st.session_state.ada)
    parsel = st.text_input("Parsel No", value=st.session_state.parsel)
    
    imar_fonksiyonu = st.selectbox(
        "İmar Fonksiyon Alanı",
        ["KONUT ALANI", "TİCARET VE KONUT ALANI", "TİCARET ALANI"]
    )
    
    yapi_tipolojisi = st.selectbox(
        "Mimar Yapı Tipolojisi Tercihi",
        ["Müstakil Villa", "İkiz Villa", "Bahçe - Çatı Dubleksi", "Standart Daire / Konut"]
    )

    tapu_alani = st.number_input("Tapu Alanı (m²)", value=float(st.session_state.tapu_alani), step=10.0)
    nitelik = st.selectbox("Nitelik", ["Bahçe", "Arsa", "Tarla"])
    terk_durumu = st.checkbox("18. Madde Terki Yapıldı mı?", value=False)
    
    kaks = st.number_input("KAKS (Emsal)", value=float(st.session_state.kaks), step=0.05)
    taks = st.number_input("TAKS", value=float(st.session_state.taks), step=0.05)
    sunum_tipi = st.selectbox("Sunum Modeli", ["Satılık", "Kat Karşılığı"])

    st.header("3. Finansal Parametreler ($ USD)")
    birim_maliyeti_usd = st.number_input("M² İnşaat Maliyeti ($)", value=750, step=50)
    satis_m2_fiyati_usd = st.number_input("M² Satış Fiyatı ($)", value=2800, step=100)
    kat_karsiligi_orani = st.slider("Kat Karşılığı Payı (%)", 30, 60, 50)
    unite_m2 = st.number_input("Ortalama Ünite Brüt m²", value=200, step=10)

# Hesaplama Mantığı
if terk_durumu or nitelik.lower() == 'arsa':
    net_alan = tapu_alani
    kesinti_orani = 0.0
    terk_str = "18. Madde Uygulanmış (Terk Yapılmış)"
else:
    net_alan = tapu_alani * 0.70
    kesinti_orani = 0.30
    terk_str = "18. Madde Dışında (%30 Kesinti)"

net_emsal_alani = net_alan * kaks
ilave_emsal_harici = net_emsal_alani * 0.30
toplam_brut_insaat = net_emsal_alani * 1.30
max_taban_alani = net_alan * taks

toplam_unite_adedi = int(toplam_brut_insaat / unite_m2)
toplam_insaat_maliyeti_usd = toplam_brut_insaat * birim_maliyeti_usd
toplam_proje_geliri_usd = toplam_brut_insaat * satis_m2_fiyati_usd

if sunum_tipi == "Kat Karşılığı":
    mutaahhit_payi_m2 = toplam_brut_insaat * (100 - kat_karsiligi_orani) / 100
    arsa_sahibi_payi_m2 = toplam_brut_insaat * kat_karsiligi_orani / 100
    mutaahhit_net_kar_usd = (mutaahhit_payi_m2 * satis_m2_fiyati_usd) - toplam_insaat_maliyeti_usd
else:
    mutaahhit_net_kar_usd = toplam_proje_geliri_usd - toplam_insaat_maliyeti_usd

# Sekmeli Detay Ekranı
tab1, tab2, tab3 = st.tabs(["📐 İmar & Kapasite Analizi", "🏗️ Mimari Potansiyel & Tipoloji", "💰 Finansal Fizibilite ($ USD)"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Brüt Arazi Alanı", f"{tapu_alani:,.2f} m²")
    c2.metric("Hesaba Esas Net Alan", f"{net_alan:,.2f} m²", delta=f"-%{int(kesinti_orani*100)} DOP" if kesinti_orani > 0 else "Kesintisiz")
    c3.metric("Net Emsal Alanı", f"{net_emsal_alani:,.2f} m²")
    c4.metric("TOPLAM BRÜT İNŞAAT", f"{toplam_brut_insaat:,.2f} m²")

    st.markdown("#### İmar Parametre Detayları")
    df_imar = pd.DataFrame({
        "Parametre": ["İmar Fonksiyonu", "Yapı Tipolojisi", "Terk/DOP Durumu", "Uygulanan KAKS (Emsal)", "TAKS (Taban Alanı Katsayısı)", "Max Taban Alanı", "%30 İlave Emsal Harici"],
        "Değer": [imar_fonksiyonu, yapi_tipolojisi, terk_str, f"{kaks:.2f}", f"{taks:.2f}", f"{max_taban_alani:,.2f} m²", f"{ilave_emsal_harici:,.2f} m²"]
    })
    st.table(df_imar)

with tab2:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown(f"#### Bölgesel Mimari Yapı Planlaması ({imar_fonksiyonu})")
        st.write(f"* **Tercih Edilen Tipoloji:** {yapi_tipolojisi}")
        st.write(f"* **Ortalama Ünite Büyüklüğü:** {unite_m2} m²")
        st.write(f"* **Tahmini Bağımsız Bölüm Sayısı:** ~{toplam_unite_adedi} Adet")
        st.write(f"* **Taban Oturumu (TAKS Sınırı):** ~{max_taban_alani:,.2f} m²")
    with col_m2:
        if sunum_tipi == "Kat Karşılığı":
            st.markdown(f"#### Kat Karşılığı Paylaşım Modeli (%{kat_karsiligi_orani} Arsa / %{100-kat_karsiligi_orani} Müteahhit)")
            st.write(f"* **Arsa Sahibi Kalan Brüt İnşaat:** {arsa_sahibi_payi_m2:,.2f} m² (~{int(arsa_sahibi_payi_m2/unite_m2)} Ünite)")
            st.write(f"* **Müteahhit Kalan Brüt İnşaat:** {mutaahhit_payi_m2:,.2f} m² (~{int(mutaahhit_payi_m2/unite_m2)} Ünite)")

with tab3:
    f1, f2, f3 = st.columns(3)
    f1.metric("Toplam İnşaat Maliyeti", f"${toplam_insaat_maliyeti_usd:,.0f}")
    f2.metric("Toplam Proje Ciro Hacmi", f"${toplam_proje_geliri_usd:,.0f}")
    f3.metric("Tahmini Net Kar / Proje Marjı", f"${mutaahhit_net_kar_usd:,.0f}")

# PDF Oluşturma Metodu (Çift Logo ve Dolar Destekli)
def kapsamli_pdf_olustur():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    story = []
    styles = getSampleStyleSheet()

    # Logoları Yan Yana Ekleme
    try:
        img_ist = RLImage("istestate_logo.png", width=120, height=45)
        img_mer = RLImage("meric_insaat_emlak_logo.png", width=160, height=45)
        logo_table = Table([[img_ist, img_mer]], colWidths=[270, 270])
        logo_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (1,0), (1,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(logo_table)
        story.append(Spacer(1, 10))
    except Exception:
        pass

    title_style = ParagraphStyle('T1', parent=styles['Heading1'], fontSize=11, textColor=colors.HexColor('#1A2B4C'), alignment=1)
    sub_style = ParagraphStyle('T2', parent=styles['Normal'], fontSize=8, textColor=colors.HexColor('#555555'), alignment=1, spaceAfter=8)

    story.append(Paragraph(tr_fix("ISTESTATE MERIC GAYRIMENKUL DANIŞMANLIK & MERIC INSAAT EMLAK"), title_style))
    story.append(Paragraph(tr_fix(f"DETAYLI TAŞINMAZ IMAR, MIMARI & FINANSAL FIZIBILITE RAPORU ({sunum_tipi.upper()})"), sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1A2B4C'), spaceAfter=10))

    data_summary = [
        [tr_fix("Mahalle / Ada / Parsel"), tr_fix(f"{mahalle} / {ada} / {parsel}"), tr_fix("Imar Fonksiyonu"), tr_fix(imar_fonksiyonu)],
        [tr_fix("Yapı Tipolojisi"), tr_fix(yapi_tipolojisi), tr_fix("Nitelik / Terk"), tr_fix(f"{nitelik} / {terk_str}")],
        [tr_fix("Tapu Alanı"), f"{tapu_alani:,.2f} m2", tr_fix("Hesaba Esas Net Alan"), f"{net_alan:,.2f} m2"],
        [tr_fix("Toplam Brüt İnşaat"), f"{toplam_brut_insaat:,.2f} m2", tr_fix("Tahmini Unite Sayısı"), f"~{toplam_unite_adedi} Adet ({unite_m2}m2)"],
        [tr_fix("Toplam Proje Ciro Hacmi"), f"${toplam_proje_geliri_usd:,.0f}", tr_fix("Tahmini Net Kar ($)"), f"${mutaahhit_net_kar_usd:,.0f}"]
    ]
    
    t_sum = Table(data_summary, colWidths=[130, 140, 130, 140])
    t_sum.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8F9FA')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_sum)
    story.append(Spacer(1, 15))

    iletisim = tr_fix("<b>Istestate Meriç Gayrimenkul Danışmanlık & Meriç İnşaat Emlak</b><br/>" \
               "Umutcan K. MERIC (0539 451 61 61) | Süleyman MERIC (0532 695 10 83)<br/>" \
               "<b>Adres:</b> Ciftlik Mah. Cavusbasi Cumhuriyet Cad. No:171/3 Beykoz/ISTANBUL")
    story.append(Paragraph(iletisim, styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

st.divider()
st.download_button(
    label="📄 Kurumsal PDF Raporunu İndir ($ USD)",
    data=kapsamli_pdf_olustur(),
    file_name=f"{mahalle}_{ada}_{parsel}_USD_Fizibilite.pdf",
    mime="application/pdf"
)
