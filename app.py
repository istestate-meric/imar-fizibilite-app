import streamlit as st
import pandas as pd
import io
from parser import parse_imar_pdf

st.set_page_config(page_title="İmar & Portföy Analiz Raporu", layout="wide")

st.title("🏢 İstestate & Meriç Gayrimenkul İmar Analiz Sistemi")

uploaded_files = st.file_uploader("İmar Durumu PDF Dosyalarını Yükleyin", type=["pdf"], accept_multiple_files=True)

if uploaded_files:
    kayitlar = []
    
    for pdf in uploaded_files:
        p = parse_imar_pdf(pdf)
        
        # HESAPLAMA MANTIĞI (Meriç Raporu Standartları):
        # Terk Yapılmamışsa Hesaba Alınan Alan = Tapu Alanı x 0.70
        # Terk Yapılmışsa Hesaba Alınan Alan = Tapu Alanı (doğrudan)
        if p["terk_yapilmis_mi"]:
            hesaba_alinan_alan = p["tapu_alani"]
            terk_statu = "Terk Yapılmış (Net)"
            formul_str = f"{p['tapu_alani']} x {p['kaks']} x 1.30"
        else:
            hesaba_alinan_alan = p["tapu_alani"] * 0.70
            terk_statu = "Terk Yapılmamış (Brüt)"
            formul_str = f"{p['tapu_alani']} x 0.70 x {p['kaks']} x 1.30"

        # Toplam İnşaat Alanı = Hesaba Alınan Alan x KAKS x 1.30
        toplam_insaat = hesaba_alinan_alan * p["kaks"] * 1.30

        kayitlar.append({
            "Dosya Adı": p["dosya_adi"],
            "Mahalle": p["mahalle"],
            "Ada/Parsel": p["ada_parsel"],
            "Tapu Alanı (m²)": round(p["tapu_alani"], 2),
            "Fonksiyon Alanı (m²)": round(p["fonksiyon_alani"], 2),
            "Terk Statüsü": terk_statu,
            "KAKS": p["kaks"],
            "Hesaba Alınan Alan (m²)": round(hesaba_alinan_alan, 2),
            "Formül": formul_str,
            "Toplam İnşaat Alanı (m²)": round(toplam_insaat, 2)
        })

    df = pd.DataFrame(kayitlar)
    
    # Tabloyu Ekranlama
    st.subheader("📊 Analiz Sonuçları")
    st.dataframe(df, use_container_width=True)

    # Excel İndirme
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='İmar Analiz')
    
    st.download_button(
        label="📥 Excel Raporunu İndir",
        data=output.getvalue(),
        file_name="Imar_Analiz_Raporu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
