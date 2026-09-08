import io
import json
import re
import urllib.request
import pandas as pd
import streamlit as st
import pdfplumber
import google.generativeai as genai
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Sayfa Yapılandırması
st.set_page_config(page_title="İstestate Meriç - İmar & Fizibilite Portalı", layout="wide")

# ReportLab Türkçe Font Kaydı (DejaVuSans Otomatik Yükleme)
@st.cache_resource
def register_fonts():
    try:
        font_url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
        font_bold_url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans-Bold.ttf"
        
        urllib.request.urlretrieve(font_url, "DejaVuSans.ttf")
        urllib.request.urlretrieve(font_bold_url, "DejaVuSans-Bold.ttf")
        
        pdfmetrics.registerFont(TTFont('DejaVuSans', 'DejaVuSans.ttf'))
        pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', 'DejaVuSans-Bold.ttf'))
        return True
    except Exception as e:
        return False

fonts_loaded = register_fonts()
FONT_NAME = 'DejaVuSans' if fonts_loaded else 'Helvetica'
FONT_BOLD = 'DejaVuSans-Bold' if fonts_loaded else 'Helvetica-Bold'

# API Key Secrets kontrolü
try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    gemini_api_key = None

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
        "Mimari Yapı Tipolojisi Tercihi",
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
    terk_str = "18. Madde Terki Yapılmış"
else:
    net_alan = tapu_alani * 0.70
    kesinti_orani = 0.30
    terk_str = "18. Madde Terksiz (%30 DOP)"

net_emsal_alani = net_alan * kaks
ilave_emsal_harici = net_emsal_alani * 0.30
toplam_brut_insaat = net_emsal_alani * 1.30
max_taban_alani = net_alan * taks

toplam_unite_adedi = int(toplam_brut_insaat / unite_m2) if unite_m2 > 0 else 0
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

# PDF Oluşturma Metodu (Yatay Format & Profesyonel Tablo Tasarımı)
def yatay_pdf_olustur():
    buffer = io.BytesIO()
    # Yatay A4 formatı
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4), 
        rightMargin=30, 
        leftMargin=30, 
        topMargin=20, 
        bottomMargin=20
    )
    story = []
    styles = getSampleStyleSheet()

    # Logolar ve Üst Başlık Tablosu
    try:
        img_ist = RLImage("istestate_logo.png", width=140, height=45)
        img_mer = RLImage("meric_insaat_emlak_logo.png", width=160, height=45)
        
        header_text = Paragraph(
            f"<b>İSTESTATE & MERİÇ İNŞAAT EMLAK</b><br/>"
            f"<font size=9 color='#C0392B'><b>PARSEL BAZLI DETAY & MİMARİ POTANSİYEL ANALİZ RAPORU</b></font>",
            ParagraphStyle('HText', fontName=FONT_BOLD, fontSize=11, leading=14, alignment=1)
        )
        
        header_table = Table([[img_ist, header_text, img_mer]], colWidths=[180, 422, 180])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (1,0), (1,0), 'CENTER'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 10))
    except Exception:
        pass

    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1A2B4C'), spaceAfter=10))

    # Hücre İçi Metin Stilleri
    th_style = ParagraphStyle('TH', fontName=FONT_BOLD, fontSize=8, textColor=colors.white, alignment=1)
    td_style = ParagraphStyle('TD', fontName=FONT_NAME, fontSize=8, textColor=colors.HexColor('#2C3E50'), alignment=1)
    td_bold = ParagraphStyle('TDBold', fontName=FONT_BOLD, fontSize=8, textColor=colors.HexColor('#1A2B4C'), alignment=1)

    # Tablo 1: Parsel Bazlı Detay Tablosu
    st_title = ParagraphStyle('SubTitle', fontName=FONT_BOLD, fontSize=9, textColor=colors.HexColor('#1A2B4C'), spaceAfter=5)
    story.append(Paragraph("1. PARSEL BAZLI DETAY TABLOSU", st_title))

    headers_t1 = [
        Paragraph("MAHALLE", th_style),
        Paragraph("ADA", th_style),
        Paragraph("PARSEL", th_style),
        Paragraph("NİTELİK", th_style),
        Paragraph("PARSEL ALANI (M²)", th_style),
        Paragraph("NET ALAN (M²)", th_style),
        Paragraph("FONKSİYON", th_style),
        Paragraph("KAKS", th_style),
        Paragraph("NET İNŞAAT (M²)", th_style),
        Paragraph("BRÜT İNŞAAT (M²)", th_style)
    ]

    row_t1 = [
        Paragraph(mahalle, td_style),
        Paragraph(ada, td_style),
        Paragraph(parsel, td_style),
        Paragraph(nitelik, td_style),
        Paragraph(f"{tapu_alani:,.2f}", td_style),
        Paragraph(f"{net_alan:,.2f}", td_style),
        Paragraph(imar_fonksiyonu, td_style),
        Paragraph(f"{kaks:.2f}", td_style),
        Paragraph(f"{net_emsal_alani:,.2f}", td_style),
        Paragraph(f"{toplam_brut_insaat:,.2f}", td_bold)
    ]

    table1 = Table([headers_t1, row_t1], colWidths=[80, 50, 50, 75, 95, 85, 115, 45, 95, 92])
    table1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1A2B4C')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F8F9FA')),
    ]))
    story.append(table1)
    story.append(Spacer(1, 12))

    # Tablo 2: Mimari Potansiyel & Finansal Özet Tablosu
    story.append(Paragraph("2. MİMARİ POTANSİYEL VE FİNANSAL FİZİBİLİTE ANALİZİ ($ USD)", st_title))

    headers_t2 = [
        Paragraph("YAPI TİPOLOJİSİ", th_style),
        Paragraph("ÜNİTE BRÜT M²", th_style),
        Paragraph("TAHMİNİ ÜNİTE ADEDİ", th_style),
        Paragraph("M² MALİYET ($)", th_style),
        Paragraph("TOPLAM MALİYET ($)", th_style),
        Paragraph("M² SATIŞ ($)", th_style),
        Paragraph("TOPLAM CIRO ($)", th_style),
        Paragraph("NET KAR MARJI ($)", th_style)
    ]

    row_t2 = [
        Paragraph(yapi_tipolojisi, td_style),
        Paragraph(f"{unite_m2} m²", td_style),
        Paragraph(f"~{toplam_unite_adedi} Adet", td_style),
        Paragraph(f"${birim_maliyeti_usd:,.0f}", td_style),
        Paragraph(f"${toplam_insaat_maliyeti_usd:,.0f}", td_style),
        Paragraph(f"${satis_m2_fiyati_usd:,.0f}", td_style),
        Paragraph(f"${toplam_proje_geliri_usd:,.0f}", td_style),
        Paragraph(f"${mutaahhit_net_kar_usd:,.0f}", td_bold)
    ]

    table2 = Table([headers_t2, row_t2], colWidths=[110, 80, 95, 80, 105, 80, 115, 117])
    table2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2C3E50')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('PADDING', (0,0), (-1,-1), 6),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F8F9FA')),
    ]))
    story.append(table2)
    story.append(Spacer(1, 15))

    # Alt Bilgi ve İletişim
    footer_style = ParagraphStyle('Footer', fontName=FONT_NAME, fontSize=8, textColor=colors.HexColor('#555555'), leading=11)
    iletisim = f"<b>İstestate Meriç Gayrimenkul Danışmanlık & Meriç İnşaat Emlak</b> | " \
               f"Umutcan K. MERİÇ (0539 451 61 61) - Süleyman MERİÇ (0532 695 10 83)<br/>" \
               f"<b>Adres:</b> Çiftlik Mah. Çavuşbaşı Cumhuriyet Cad. No:171/3 Beykoz/İSTANBUL"
    story.append(Paragraph(iletisim, footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

st.divider()
st.download_button(
    label="📄 Yatay Formatlı Kurumsal PDF Raporunu İndir ($ USD)",
    data=yatay_pdf_olustur(),
    file_name=f"{mahalle}_{ada}_{parsel}_Yatay_Fizibilite.pdf",
    mime="application/pdf"
)
