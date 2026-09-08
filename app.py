import io
import json
import pandas as pd
import streamlit as st
import pdfplumber
import google.generativeai as genai
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Sayfa Yapılandırması
st.set_page_config(page_title="İstestate Meriç - İmar & Fizibilite Portalı", layout="wide")

# Kurumsal Başlık
st.title("İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK & MERİÇ İNŞAAT EMLAK")
st.subheader("Gelişmiş Taşınmaz İmar, Mimari Potansiyel ve Finansal Fizibilite Paneli")
st.divider()

# Yan Panel - PDF Yükleme ve Manuel Girdiler
with st.sidebar:
    st.header("1. Belge ile Otomatik Analiz")
    uploaded_pdf = st.file_uploader("İmar Durumu PDF Raporu Yükleyin", type=["pdf"])
    gemini_api_key = st.text_input("Gemini API Key (Opsiyonel OCR için)", type="password")

    st.header("2. Parsel & İmar Parametreleri")
    mahalle = st.text_input("Mahalle", "Çengeldere")
    ada = st.text_input("Ada No", "1437")
    parsel = st.text_input("Parsel No", "17")
    tapu_alani = st.number_input("Tapu Alanı (m²)", value=6398.86, step=10.0)
    nitelik = st.selectbox("Nitelik", ["Bahçe", "Arsa", "Tarla"])
    terk_durumu = st.checkbox("18. Madde Terki Yapıldı mı?", value=False)
    
    kaks = st.number_input("KAKS (Emsal)", value=0.40, step=0.05)
    taks = st.number_input("TAKS", value=0.30, step=0.05)
    sunum_tipi = st.selectbox("Sunum Modeli", ["Kat Karşılığı", "Satılık"])

    st.header("3. Finansal & Mimari Varsayımlar")
    birim_maliyeti = st.number_input("M² İnşaat Maliyeti (TL)", value=25000, step=1000)
    satis_m2_fiyati = st.number_input("M² Satış Fiyatı (TL)", value=85000, step=5000)
    kat_karsiligi_orani = st.slider("Kat Karşılığı Payı (%)", 30, 60, 50)
    daire_m2 = st.number_input("Ort. Daire Brüt m²", value=120, step=10)

# PDF Ayrıştırma Mantığı
if uploaded_pdf is not None:
    with pdfplumber.open(uploaded_pdf) as pdf:
        extracted_text = "\n".join([page.extract_text() or "" for page in pdf.pages])
    st.sidebar.success("PDF İçeriği Okundu!")
    
    # API Anahtarı Varsa AI Ayıklama
    if gemini_api_key:
        try:
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            prompt = f"Aşağıdaki imar raporu metninden şu bilgileri JSON formatında çıkar: mahalle, ada, parsel, tapu_alani, kaks, taks. Metin: {extracted_text[:2000]}"
            response = model.generate_content(prompt)
            st.sidebar.json(response.text)
        except Exception as e:
            st.sidebar.warning(f"AI Ayıklama Yapılamadı: {e}")

# Matematiksel Fizibilite Hesaplamaları
if terk_durumu or nitelik.lower() == 'arsa':
    net_alan = tapu_alani
    kesinti_orani = 0.0
    terk_str = "18. Madde Uygulanmış (Terk Yapılmış)"
else:
    net_alan = tapu_alani * 0.70
    kesinti_orani = 0.30
    terk_str = "18. Madde Dışında (Terk Yapılmamış - %30 Kesinti)"

net_emsal_alani = net_alan * kaks
ilave_emsal_harici = net_emsal_alani * 0.30
toplam_brut_insaat = net_emsal_alani * 1.30
max_taban_alani = net_alan * taks

# Mimari & Finansal Metrikler
toplam_daire_adedi = int(toplam_brut_insaat / daire_m2)
toplam_insaat_maliyeti = toplam_brut_insaat * birim_maliyeti
toplam_proje_geliri = toplam_brut_insaat * satis_m2_fiyati

# Sunum Modeline Göre Finansal Ayrışma
if sunum_tipi == "Kat Karşılığı":
    mutaahhit_payi_m2 = toplam_brut_insaat * (100 - kat_karsiligi_orani) / 100
    arsa_sahibi_payi_m2 = toplam_brut_insaat * kat_karsiligi_orani / 100
    mutaahhit_net_kar = (mutaahhit_payi_m2 * satis_m2_fiyati) - toplam_insaat_maliyeti
else:
    mutaahhit_net_kar = toplam_proje_geliri - toplam_insaat_maliyeti

# Sekmeli Detay Ekranı
tab1, tab2, tab3 = st.tabs(["📐 İmar & Kapasite Analizi", "🏗️ Mimari Potansiyel", "💰 Finansal Fizibilite"])

with tab1:
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Brüt Arazi Alanı", f"{tapu_alani:,.2f} m²")
    c2.metric("Hesaba Esas Net Alan", f"{net_alan:,.2f} m²", delta=f"-%{int(kesinti_orani*100)} DOP" if kesinti_orani > 0 else "Kesintisiz")
    c3.metric("Net Emsal Alanı", f"{net_emsal_alani:,.2f} m²")
    c4.metric("TOPLAM BRÜT İNŞAAT", f"{toplam_brut_insaat:,.2f} m²")

    st.markdown("#### İmar Parametre Detayları")
    df_imar = pd.DataFrame({
        "Parametre": ["Terk/DOP Durumu", "Uygulanan KAKS (Emsal)", "TAKS (Taban Alanı Katsayısı)", "Max Taban Alanı", "%30 İlave Emsal Harici"],
        "Değer": [terk_str, f"{kaks:.2f}", f"{taks:.2f}", f"{max_taban_alani:,.2f} m²", f"{ilave_emsal_harici:,.2f} m²"]
    })
    st.table(df_imar)

with tab2:
    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("#### Tahmini Bağımsız Bölüm Kapasitesi")
        st.write(f"* **Ortalama Daire Büyüklüğü:** {daire_m2} m²")
        st.write(f"* **Tahmini Toplam Konut/Daire Adedi:** ~{toplam_daire_adedi} Adet")
        st.write(f"* **Kat Sayısı/Taban Mimarisi:** Oturum alanı ~{max_taban_alani:,.2f} m² sınırına göre projelendirilebilir.")
    with col_m2:
        if sunum_tipi == "Kat Karşılığı":
            st.markdown(f"#### Kat Karşılığı Paylaşım Modeli (%{kat_karsiligi_orani} Arsa / %{100-kat_karsiligi_orani} Müteahhit)")
            st.write(f"* **Arsa Sahibi Kalan Brüt İnşaat:** {arsa_sahibi_payi_m2:,.2f} m² (~{int(arsa_sahibi_payi_m2/daire_m2)} Daire)")
            st.write(f"* **Müteahhit Kalan Brüt İnşaat:** {mutaahhit_payi_m2:,.2f} m² (~{int(mutaahhit_payi_m2/daire_m2)} Daire)")

with tab3:
    f1, f2, f3 = st.columns(3)
    f1.metric("Toplam İnşaat Maliyeti", f"₺{toplam_insaat_maliyeti:,.0f}")
    f2.metric("Toplam Proje Ciro Hacmi", f"₺{toplam_proje_geliri:,.0f}")
    f3.metric("Tahmini Net Kar / Proje Marjı", f"₺{mutaahhit_net_kar:,.0f}")

# PDF Oluşturma Metodu
def kapsamli_pdf_olustur():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=25, leftMargin=25, topMargin=25, bottomMargin=25)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('T1', parent=styles['Heading1'], fontSize=12, textColor=colors.HexColor('#1A2B4C'), alignment=1)
    sub_style = ParagraphStyle('T2', parent=styles['Normal'], fontSize=9, textColor=colors.HexColor('#555555'), alignment=1, spaceAfter=10)

    story.append(Paragraph("<b>İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK & MERİÇ İNŞAAT EMLAK</b>", title_style))
    story.append(Paragraph(f"<b>DETAYLI TAŞINMAZ İMAR & MİMARİ FİZİBİLİTE RAPORU ({sunum_tipi.upper()})</b>", sub_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1A2B4C'), spaceAfter=10))

    data_summary = [
        ["Mahalle / Ada / Parsel", f"{mahalle} / {ada} / {parsel}", "Nitelik / Terk", f"{nitelik} / {terk_str}"],
        ["Tapu Alanı", f"{tapu_alani:,.2f} m²", "Hesaba Esas Net Alan", f"{net_alan:,.2f} m²"],
        ["Toplam Brüt İnşaat", f"{toplam_brut_insaat:,.2f} m²", "Tahmini Daire Sayısı", f"~{toplam_daire_adedi} Adet ({daire_m2}m²)"],
        ["Toplam Proje Hacmi", f"₺{toplam_proje_geliri:,.0f}", "Tahmini Net Kar", f"₺{mutaahhit_net_kar:,.0f}"]
    ]
    t_sum = Table(data_summary, colWidths=[120, 150, 120, 150])
    t_sum.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8F9FA')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('PADDING', (0,0), (-1,-1), 5),
    ]))
    story.append(t_sum)
    story.append(Spacer(1, 10))

    iletisim = "<b>İstestate Meriç Gayrimenkul Danışmanlık & Meriç İnşaat Emlak</b><br/>" \
               "Umutcan K. MERİÇ (0539 451 61 61) | Süleyman MERİÇ (0532 695 10 83)<br/>" \
               "<b>Adres:</b> Çiftlik Mah. Çavuşbaşı Cumhuriyet Cad. No:171/3 Beykoz/İSTANBUL"
    story.append(Paragraph(iletisim, styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

st.divider()
st.download_button(
    label="📄 Kapsamlı Kurumsal Fizibilite PDF Raporunu İndir",
    data=kapsamli_pdf_olustur(),
    file_name=f"{mahalle}_{ada}_{parsel}_Kapsamli_Fizibilite.pdf",
    mime="application/pdf"
)
