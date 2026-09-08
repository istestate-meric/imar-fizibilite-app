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
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Sayfa Yapılandırması
st.set_page_config(page_title="İstestate Meriç - İmar & Fizibilite Portalı", layout="wide")

# Türkçe Karakter Garanti Yükleme Sistemi
@st.cache_resource
def setup_tr_fonts():
    font_urls = {
        'TR_Sans': "https://raw.githubusercontent.com/google/fonts/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf",
        'TR_Sans_Bold': "https://raw.githubusercontent.com/google/fonts/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
    }
    
    # 1. Garanti Yöntem: Google Fonts Noto Sans TTF indirip kaydet
    try:
        url = "https://github.com/google/fonts/raw/main/ofl/dejavusans/DejaVuSans.ttf"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            pdfmetrics.registerFont(TTFont('TR_Font', io.BytesIO(data)))
            pdfmetrics.registerFont(TTFont('TR_Font_Bold', io.BytesIO(data)))
            return 'TR_Font', 'TR_Font_Bold'
    except Exception:
        pass

    # 2. İkincil Ağ Yolu (CDN)
    try:
        url = "https://cdn.jsdelivr.net/gh/dejavu-fonts/dejavu-fonts-ttf@version_2_37/ttf/DejaVuSans.ttf"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            pdfmetrics.registerFont(TTFont('TR_Font', io.BytesIO(data)))
            pdfmetrics.registerFont(TTFont('TR_Font_Bold', io.BytesIO(data)))
            return 'TR_Font', 'TR_Font_Bold'
    except Exception:
        pass

    # 3. Son Çare: Türkçe karakterleri ASCII muadillerine dönüştüren tam emniyet mekanizması
    return None, None

FONT_NAME, FONT_BOLD = setup_tr_fonts()

def tr_fix(text):
    """Eğer sistemde TTF font yüklenemezse PDF'in kırılmaması ve kare (■) çıkmaması için Türkçe metni dönüştürür."""
    if FONT_NAME is not None:
        return str(text)
    
    mapping = {
        'İ': 'I', 'I': 'I', 'ı': 'i',
        'Ş': 'S', 'ş': 's',
        'Ğ': 'G', 'ğ': 'g',
        'Ç': 'C', 'ç': 'c',
        'Ö': 'O', 'ö': 'o',
        'Ü': 'U', 'ü': 'u'
    }
    text_str = str(text)
    for k, v in mapping.items():
        text_str = text_str.replace(k, v)
    return text_str

# Font tanımlamaları varsayılana düşerse ASCII güvenliği sağlanır
USE_FONT = FONT_NAME if FONT_NAME else 'Helvetica'
USE_FONT_BOLD = FONT_BOLD if FONT_BOLD else 'Helvetica-Bold'

# Gemini API Key Secrets Kontrolü
try:
    gemini_api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    gemini_api_key = None

# Session State
if "mahalle" not in st.session_state: st.session_state.mahalle = "Yavuzselim"
if "ada" not in st.session_state: st.session_state.ada = "1658"
if "parsel" not in st.session_state: st.session_state.parsel = "1"
if "tapu_alani" not in st.session_state: st.session_state.tapu_alani = 6721.92
if "kaks" not in st.session_state: st.session_state.kaks = 0.45
if "taks" not in st.session_state: st.session_state.taks = 0.30

col_l1, col_l2 = st.columns([1, 4])
with col_l1:
    try: st.image("istestate_logo.png", width=180)
    except Exception: pass
with col_l2:
    st.title("İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK & MERİÇ İNŞAAT EMLAK")
    st.subheader("Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli")

st.divider()

# Sol Panel (Girdiler)
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
    
    imar_fonksiyonu = st.selectbox("İmar Fonksiyon Alanı", ["KONUT ALANI", "TİCARET VE KONUT ALANI", "TİCARET ALANI"])
    yapi_tipolojisi = st.selectbox("Mimari Yapı Tipolojisi Tercihi", ["Müstakil Villa", "İkiz Villa", "Bahçe - Çatı Dubleksi", "Standart Daire / Konut"])

    tapu_alani = st.number_input("Tapu Alanı (m²)", value=float(st.session_state.tapu_alani), step=10.0)
    nitelik = st.selectbox("Nitelik", ["Bahçe", "Arsa", "Tarla"])
    terk_durumu = st.checkbox("18. Madde Terki Yapıldı mı?", value=False)
    
    kaks = st.number_input("KAKS (Emsal)", value=float(st.session_state.kaks), step=0.05)
    taks = st.number_input("TAKS", value=float(st.session_state.taks), step=0.05)
    sunum_tipi = st.selectbox("Sunum Modeli", ["Satılık", "Kat Karşılığı"])

    st.header("3. Finansal Parametreler ($ USD)")
    birim_maliyeti_usd = st.number_input("M² İnşaat Maliyeti ($)", value=1200, step=50)
    satis_m2_fiyati_usd = st.number_input("M² Satış Fiyatı ($)", value=5000, step=100)
    kat_karsiligi_orani = st.slider("Kat Karşılığı Payı (%)", 30, 60, 50)
    unite_m2 = st.number_input("Ortalama Ünite Brüt m²", value=200, step=10)

# Hesaplamalar
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

# Arayüz Sekmeleri
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

# PDF Oluşturma Fonksiyonu
def yatay_kurumsal_pdf_olustur():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=landscape(A4), 
        rightMargin=20, 
        leftMargin=20, 
        topMargin=20, 
        bottomMargin=20
    )
    story = []

    # Stil Tanımlamaları
    banner_title = ParagraphStyle('BTitle', fontName=USE_FONT_BOLD, fontSize=11, textColor=colors.white, alignment=1, leading=14)
    th_style = ParagraphStyle('TH', fontName=USE_FONT_BOLD, fontSize=7.5, textColor=colors.white, alignment=1, leading=9)
    td_style = ParagraphStyle('TD', fontName=USE_FONT, fontSize=8, textColor=colors.HexColor('#1E293B'), alignment=1, leading=10)
    td_bold = ParagraphStyle('TDBold', fontName=USE_FONT_BOLD, fontSize=8, textColor=colors.HexColor('#0F172A'), alignment=1, leading=10)
    section_title = ParagraphStyle('SecTitle', fontName=USE_FONT_BOLD, fontSize=9, textColor=colors.HexColor('#1B2A47'), spaceAfter=5)
    footer_style = ParagraphStyle('Footer', fontName=USE_FONT, fontSize=7.5, textColor=colors.HexColor('#475569'), leading=11)

    # Logolar
    try:
        img_ist = RLImage("istestate_logo.png", width=140, height=42)
        img_mer = RLImage("meric_insaat_emlak_logo.png", width=150, height=42)
        
        box_ist = Table([[img_ist]], colWidths=[146])
        box_ist.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ]))

        box_mer = Table([[img_mer]], colWidths=[156])
        box_mer.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
            ('LEFTPADDING', (0,0), (-1,-1), 3),
            ('RIGHTPADDING', (0,0), (-1,-1), 3),
        ]))

        banner_text = Paragraph(
            f"<b>{tr_fix('İSTESTATE & MERİÇ İNŞAAT EMLAK')}</b><br/>"
            f"<font size=8 color='#E2E8F0'>{tr_fix('DETAYLI İMAR, MİMARİ POTANSİYEL VE FİNANSAL FİZİBİLİTE RAPORU')}</font>", 
            banner_title
        )
        
        banner_table = Table([[box_ist, banner_text, box_mer]], colWidths=[156, 490, 156])
        banner_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#1B2A47')),
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (1,0), (1,0), 'CENTER'),
            ('ALIGN', (2,0), (2,0), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('LEFTPADDING', (0,0), (-1,-1), 6),
            ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 14))
    except Exception:
        pass

    # Tablo 1
    story.append(Paragraph(tr_fix("1. PARSEL BAZLI DETAY TABLOSU"), section_title))

    headers_t1 = [
        Paragraph(tr_fix("MAHALLE"), th_style),
        Paragraph(tr_fix("ADA"), th_style),
        Paragraph(tr_fix("PARSEL"), th_style),
        Paragraph(tr_fix("NİTELİK"), th_style),
        Paragraph(tr_fix("PARSEL ALANI (M²)"), th_style),
        Paragraph(tr_fix("NET ALAN (M²)"), th_style),
        Paragraph(tr_fix("FONKSİYON"), th_style),
        Paragraph(tr_fix("KAKS"), th_style),
        Paragraph(tr_fix("NET İNŞAAT (M²)"), th_style),
        Paragraph(tr_fix("BRÜT İNŞAAT (M²)"), th_style)
    ]

    row_t1 = [
        Paragraph(tr_fix(mahalle), td_style),
        Paragraph(tr_fix(str(ada)), td_style),
        Paragraph(tr_fix(str(parsel)), td_style),
        Paragraph(tr_fix(nitelik), td_style),
        Paragraph(f"{tapu_alani:,.2f}", td_style),
        Paragraph(f"{net_alan:,.2f}", td_style),
        Paragraph(tr_fix(imar_fonksiyonu), td_style),
        Paragraph(f"{kaks:.2f}", td_style),
        Paragraph(f"{net_emsal_alani:,.2f}", td_style),
        Paragraph(f"{toplam_brut_insaat:,.2f}", td_bold)
    ]

    table1 = Table([headers_t1, row_t1], colWidths=[80, 45, 45, 70, 95, 90, 125, 45, 100, 107])
    table1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1B2A47')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F8FAFC')),
    ]))
    story.append(table1)
    story.append(Spacer(1, 14))

    # Tablo 2
    story.append(Paragraph(tr_fix("2. MİMARİ POTANSİYEL VE FİNANSAL FİZİBİLİTE ANALİZİ ($ USD)"), section_title))

    headers_t2 = [
        Paragraph(tr_fix("YAPI TİPOLOJİSİ"), th_style),
        Paragraph(tr_fix("ÜNİTE BRÜT M²"), th_style),
        Paragraph(tr_fix("TAHMİNİ ÜNİTE ADEDİ"), th_style),
        Paragraph(tr_fix("M² MALİYET ($)"), th_style),
        Paragraph(tr_fix("TOPLAM MALİYET ($)"), th_style),
        Paragraph(tr_fix("M² SATIŞ ($)"), th_style),
        Paragraph(tr_fix("TOPLAM CİRO ($)"), th_style),
        Paragraph(tr_fix("NET KAR MARJI ($)"), th_style)
    ]

    row_t2 = [
        Paragraph(tr_fix(yapi_tipolojisi), td_style),
        Paragraph(f"{unite_m2} m²", td_style),
        Paragraph(f"~{toplam_unite_adedi} Adet", td_style),
        Paragraph(f"${birim_maliyeti_usd:,.0f}", td_style),
        Paragraph(f"${toplam_insaat_maliyeti_usd:,.0f}", td_style),
        Paragraph(f"${satis_m2_fiyati_usd:,.0f}", td_style),
        Paragraph(f"${toplam_proje_geliri_usd:,.0f}", td_style),
        Paragraph(f"${mutaahhit_net_kar_usd:,.0f}", td_bold)
    ]

    table2 = Table([headers_t2, row_t2], colWidths=[110, 80, 95, 80, 110, 80, 120, 127])
    table2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2A3B5C')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CBD5E1')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('BACKGROUND', (0,1), (-1,1), colors.HexColor('#F8FAFC')),
    ]))
    story.append(table2)
    story.append(Spacer(1, 16))

    # Alt Bilgi
    iletisim = tr_fix("<b>İstestate Meriç Gayrimenkul Danışmanlık & Meriç İnşaat Emlak</b> | ") + \
               tr_fix(f"Umutcan K. MERİÇ (0539 451 61 61) - Süleyman MERİÇ (0532 695 10 83)<br/>") + \
               tr_fix(f"<b>Adres:</b> Çiftlik Mah. Çavuşbaşı Cumhuriyet Cad. No:171/3 Beykoz/İSTANBUL")
    story.append(Paragraph(iletisim, footer_style))

    doc.build(story)
    buffer.seek(0)
    return buffer

clean_mahalle = re.sub(r'[^\w\s-]', '', mahalle).strip().replace(" ", "_")
kurumsal_dosya_adi = f"ISTESTATE_MERIC_Fizibilite_Raporu_{clean_mahalle}_{ada}_{parsel}_2026.pdf"

st.divider()
st.download_button(
    label="📄 Kurumsal PDF Raporunu İndir ($ USD)",
    data=yatay_kurumsal_pdf_olustur(),
    file_name=kurumsal_dosya_adi,
    mime="application/pdf"
)
