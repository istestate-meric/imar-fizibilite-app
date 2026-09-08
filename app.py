import io
import pandas as pd
import streamlit as st
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# Sayfa Yapılandırması
st.set_page_config(page_title="İmar Fizibilite Analizi", layout="wide")

st.title("İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK & MERİÇ İNŞAAT EMLAK")
st.subheader("İmar Emsal & Fizibilite Hesaplama Paneli")
st.divider()

# Sol Panel - Inputlar
with st.sidebar:
    st.header("Parsel Bilgileri")
    mahalle = st.selectbox("Mahalle", ["Yavuzselim", "Fatih", "Çengeldere", "Görele", "Çiftlik", "Baklacı"])
    ada = st.text_input("Ada No", "2421")
    parsel = st.text_input("Parsel No", "4")
    tapu_alani = st.number_input("Tapu Alanı (m²)", value=7346.76, step=10.0)
    nitelik = st.selectbox("Nitelik", ["Arsa", "Bahçe", "Tarla"])
    terk_durumu = st.checkbox("18. Madde Terki Yapıldı mı?", value=False)
    
    st.header("İmar Parametreleri")
    kaks = st.number_input("KAKS (Emsal)", value=0.45, step=0.05)
    taks = st.number_input("TAKS", value=0.30, step=0.05)
    sunum_tipi = st.selectbox("Sunum Modeli", ["Satılık", "Kat Karşılığı"])

# Hesaplama Mantığı
if terk_durumu or nitelik.lower() == 'arsa':
    net_alan = tapu_alani
    terk_str = "18. Madde Uygulanmış (Terk Yapılmış)"
    kesinti_orani = 0.0
else:
    net_alan = tapu_alani * 0.70
    terk_str = "18. Madde Dışında (Terk Yapılmamış)"
    kesinti_orani = 0.30

net_emsal = net_alan * kaks
ilave_alan = net_emsal * 0.30
toplam_brut = net_emsal * 1.30
max_taban = net_alan * taks

# Metrik Kartları
col1, col2, col3 = st.columns(3)
col1.metric("Tapu Alanı", f"{tapu_alani:,.2f} m²")
col2.metric("Hesaba Esas Net Alan", f"{net_alan:,.2f} m²", delta=f"-%{int(kesinti_orani*100)} Kesinti" if kesinti_orani > 0 else "Kesintisiz")
col3.metric("TOPLAM BRÜT İNŞAAT", f"{toplam_brut:,.2f} m²")

st.markdown("### Detaylı İmar Tablosu")
df = pd.DataFrame({
    "Hesap Kalemi": ["Net Emsal Alanı", "%30 İlave Alan (Emsal Harici)", "Max Taban Alanı (TAKS)"],
    "Alan (m²)": [f"{net_emsal:,.2f} m²", f"{ilave_alan:,.2f} m²", f"{max_taban:,.2f} m²"]
})
st.table(df)

# Süreç Akışı Bilgilendirmesi
if sunum_tipi == "Kat Karşılığı":
    surec_str = "Arsa Analizi ➔ Projelendirme ➔ Sözleşme ➔ Ruhsat ➔ İnşaat ➔ Teslim"
    st.info(f"**Süreç Akışı (Kat Karşılığı / Müteahhit):** {surec_str}")
else:
    surec_str = "Arsa Analizi ➔ Terk İşlemi ➔ Projelendirme ➔ Ruhsat ➔ İnşaat ➔ İskan"
    st.info(f"**Süreç Akışı (Satılık / Müşteri):** {surec_str}")

# PDF Oluşturma Fonksiyonu
def pdf_olustur():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    story = []
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=13, textColor=colors.HexColor('#1A2B4C'), alignment=1, spaceAfter=5)
    subtitle_style = ParagraphStyle('SubTitleStyle', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#555555'), alignment=1, spaceAfter=15)

    story.append(Paragraph("<b>İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK & MERİÇ İNŞAAT EMLAK</b>", title_style))
    story.append(Paragraph(f"<b>İMAR EMSAL & ANALİZ RAPORU ({sunum_tipi.upper()})</b>", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1A2B4C'), spaceAfter=15))

    data_tasinmaz = [
        ["Mahalle / İlçe", f"{mahalle} / Beykoz", "Nitelik", nitelik],
        ["Ada / Parsel", f"{ada} / {parsel}", "18. Madde / Terk", terk_str],
        ["Tapu Alanı", f"{tapu_alani:,.2f} m²", "Sunum Modeli", sunum_tipi]
    ]
    t1 = Table(data_tasinmaz, colWidths=[110, 160, 130, 140])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8F9FA')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,-1), 9),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t1)
    story.append(Spacer(1, 15))

    data_hesap = [
        ["Girdi / Hesap Kalemi", "Değer / Ölçü"],
        ["Hesaba Esas Net Alan", f"{net_alan:,.2f} m²"],
        ["Uygulanan Emsal (KAKS)", f"{kaks:.2f}"],
        ["Net Emsal İnşaat Alanı", f"{net_emsal:,.2f} m²"],
        ["%30 İlave Alan (Emsal Harici)", f"{ilave_alan:,.2f} m²"],
        ["TOPLAM BRÜT İNŞAAT ALANI", f"{toplam_brut:,.2f} m²"],
        ["Max Taban Alanı (TAKS)", f"{max_taban:,.2f} m²"]
    ]
    t2 = Table(data_hesap, colWidths=[270, 270])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (1,0), colors.HexColor('#1A2B4C')),
        ('TEXTCOLOR', (0,0), (1,0), colors.white),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
        ('FONTNAME', (0,5), (1,5), 'Helvetica-Bold'),
        ('BACKGROUND', (0,5), (1,5), colors.HexColor('#E2E8F0')),
        ('PADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(t2)
    story.append(Spacer(1, 15))

    story.append(Paragraph(f"<b>Süreç Akışı:</b> {surec_str}", styles['Normal']))
    story.append(Spacer(1, 15))

    iletisim = "<b>İstestate Meriç Gayrimenkul Danışmanlık & Meriç İnşaat Emlak</b><br/>" \
               "Umutcan K. MERİÇ (0539 451 61 61) | Süleyman MERİÇ (0532 695 10 83)<br/>" \
               "<b>Adres:</b> Çiftlik Mah. Çavuşbaşı Cumhuriyet Cad. No:171/3 Beykoz/İSTANBUL"
    story.append(Paragraph(iletisim, styles['Normal']))

    doc.build(story)
    buffer.seek(0)
    return buffer

# PDF İndirme Butonu
st.divider()
pdf_data = pdf_olustur()
st.download_button(
    label="📄 Kurumsal PDF Raporunu İndir",
    data=pdf_data,
    file_name=f"{mahalle}_{ada}_{parsel}_Imar_Raporu.pdf",
    mime="application/pdf"
)
