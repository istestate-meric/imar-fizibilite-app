import streamlit as st
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Sayfa Yapılandırması
st.set_page_config(page_title="İmar Fizibilite Analizi", layout="wide")

# Kurumsal Başlık
st.title("İSTESTATE MERİÇ GAYRİMENKUL DANIŞMANLIK & MERİÇ İNŞAAT EMLAK")
st.subheader("İmar Emsal & Fizibilite Hesaplama Paneli")
st.divider()

# Sol Panel - Inputlar
with st.sidebar:
    st.header("Parsel Bilgileri")
    mahalle = st.selectbox("Mahalle", ["Fatih", "Yavuzselim", "Çengeldere", "Görelis", "Çiftlik", "Baklacı"])
    ada = st.text_input("Ada No", "40")
    parsel = st.text_input("Parsel No", "70")
    tapu_alani = st.number_input("Tapu Alanı (m²)", value=1372.10, step=10.0)
    nitelik = st.selectbox("Nitelik", ["Arsa", "Bahçe", "Tarla"])
    terk_durumu = st.checkbox("18. Madde Terki Yapıldı mı?", value=False)
    
    st.header("İmar Parametreleri")
    kaks = st.number_input("KAKS (Emsal)", value=0.40, step=0.05)
    taks = st.number_input("TAKS", value=0.30, step=0.05)
    sunum_tipi = st.selectbox("Sunum Modeli", ["Kat Karşılığı", "Satılık"])

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

# Sağ Panel - Sonuç Ekranı
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

if sunum_tipi == "Kat Karşılığı":
    st.info("**Süreç Akışı (Müteahhit):** Arsa Analizi ➔ Projelendirme ➔ Sözleşme ➔ Ruhsat ➔ İnşaat ➔ Teslim")
else:
    st.info("**Süreç Akışı (Satılık):** Arsa Analizi ➔ Terk İşlemi ➔ Projelendirme ➔ Ruhsat ➔ İnşaat ➔ İskan")
