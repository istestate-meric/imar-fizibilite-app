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


# --- 1. ÇOKLU FONKSİYON VE ÇOKLU KAKS DESTEKLİ PDF PARSER ---
def parse_imar_pdf_multi_zone(uploaded_file):
    full_text = ""
    pages_text = []

    with pdfplumber.open(uploaded_file) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            pages_text.append(t)
            full_text += t + "\n"

    # Ada & Parsel Yakalama
    ada_val = "-"
    parsel_val = "-"

    ada_match = re.search(
        r"Ada\s*[:\s|]+(\d+)|Ada\s*\n\s*(\d+)", full_text, re.IGNORECASE
    )
    if ada_match:
        ada_val = ada_match.group(1) or ada_match.group(2)

    parsel_match = re.search(
        r"Parsel\s*[:\s|]+(\d+)|Parsel\s*\n\s*(\d+)", full_text, re.IGNORECASE
    )
    if parsel_match:
        parsel_val = parsel_match.group(1) or parsel_match.group(2)

    if ada_val == "-" or parsel_val == "-":
        filename_match = re.search(
            r"(\d+)\s*Ada\s*(\d+)\s*Parsel", uploaded_file.name, re.IGNORECASE
        )
        if filename_match:
            ada_val = filename_match.group(1)
            parsel_val = filename_match.group(2)

    # Toplam Alan (Tapu / Grafik Alanı)
    m2_val = 0.0
    m2_match = re.search(
        r"Alan\s*\*?[\s|:]*([\d\.,]+)\s*m²", full_text, re.IGNORECASE
    )
    if m2_match:
        raw_m2 = m2_match.group(1).replace(".", "").replace(",", ".")
        try:
            m2_val = float(raw_m2)
        except ValueError:
            m2_val = 0.0

    # Alt Fonksiyon / Çoklu İmar Bölgelerini Ayrıştırma
    fonksiyonlar = []

    # 'Fonksiyon Adı' ile başlayan blokları böl
    raw_blocks = re.split(r"Fonksiyon Adı", full_text, flags=re.IGNORECASE)

    for block in raw_blocks[1:]:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        f_adi = lines[0] if lines else "Bilinmeyen"

        # TAKS
        taks = 0.0
        taks_m = re.search(r"Taks\s*[:\s|]*(\d+[\.,]\d+)", block, re.IGNORECASE)
        if taks_m:
            taks = float(taks_m.group(1).replace(",", "."))

        # KAKS
        kaks = 0.0
        kaks_m = re.search(
            r"(Kaks|Emsal)\s*(\(Emsal\))?\s*[:\s|]*(\d+[\.,]\d+)",
            block,
            re.IGNORECASE,
        )
        if kaks_m:
            kaks = float(kaks_m.group(3).replace(",", "."))

        # Fonksiyon Alanı (m²)
        f_m2 = 0.0
        # Örn: "%99.97 - 2,581.21 m²" veya "5,995.93 m²"
        m2_f_match = re.search(
            r"([\d\.,]+)\s*m²",
            block.split("Fonksiyon Alanına")[-1]
            if "Fonksiyon Alanına" in block
            else block,
            re.IGNORECASE,
        )
        if m2_f_match:
            raw_f_m2 = m2_f_match.group(1)
            if "," in raw_f_m2 and "." in raw_f_m2:
                raw_f_m2 = raw_f_m2.replace(".", "").replace(",", ".")
            elif "," in raw_f_m2:
                raw_f_m2 = raw_f_m2.replace(",", ".")
            try:
                f_m2 = float(raw_f_m2)
            except ValueError:
                f_m2 = 0.0

        fonksiyonlar.append({
            "fonksiyon_adi": f_adi,
            "taks": taks,
            "kaks": kaks,
            "m2": f_m2,
        })

    # Ağırlıklı Ortalama KAKS & TAKS Hesaplama
    toplam_imar_m2 = sum(f["m2"] for f in fonksiyonlar if f["kaks"] > 0)
    toplam_emsal_m2 = sum(f["m2"] * f["kaks"] for f in fonksiyonlar)
    toplam_zemin_m2 = sum(f["m2"] * f["taks"] for f in fonksiyonlar)

    agirlikli_kaks = (
        toplam_emsal_m2 / toplam_imar_m2 if toplam_imar_m2 > 0 else 0.30
    )
    agirlikli_taks = (
        toplam_zemin_m2 / toplam_imar_m2 if toplam_imar_m2 > 0 else 0.30
    )

    return {
        "dosya_adi": uploaded_file.name,
        "ada": ada_val,
        "parsel": parsel_val,
        "m2": m2_val if m2_val > 0 else sum(f["m2"] for f in fonksiyonlar),
        "taks": round(agirlikli_taks, 2),
        "kaks": round(agirlikli_kaks, 2),
        "fonksiyonlar": fonksiyonlar,
    }


# --- 2. HESAPLAMA MOTORU ---
def hesapla_fizibilite(parseller_listesi, finansal_parametreler):
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
            "Ağırlıklı KAKS": kaks,
            "Emsal İnşaat m²": round(parsel_emsal_m2, 2),
        })

    toplam_brut_insaat = toplam_emsal_insaat * 1.30
    ort_kaks = (
        round(toplam_emsal_insaat / toplam_net_arazi, 4)
        if toplam_net_arazi > 0
        else 0
    )

    birim_konut_m2 = finansal_parametreler["birim_konut_m2"]
    tahmini_unite = int(toplam_brut_insaat // birim_konut_m2)

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
            "Tahmini Ünite / Konut Adedi": tahmini_unite,
        },
    }


# --- 3. STREAMLIT ARAYÜZÜ ---
st.title("🏢 Gayrimenkul İmar & Fizibilite Paneli")

st.sidebar.header("📁 Belge Yükleme (PDF)")
uploaded_files = st.sidebar.file_uploader(
    "İmar Raporu PDF'lerini Yükleyin", type=["pdf"], accept_multiple_files=True
)

st.sidebar.header("⚙️ Parametreler")
override_kaks = st.sidebar.checkbox(
    "Tevhit/Özel KAKS Kullan (PDF'leri Ez)", value=False
)
sabit_kaks = st.sidebar.number_input(
    "Birleşik KAKS", value=0.70, step=0.05, disabled=not override_kaks
)

parsel_listesi = []

if uploaded_files:
    for idx, f in enumerate(uploaded_files):
        parsed = parse_imar_pdf_multi_zone(f)

        # Çoklu Fonksiyon Detayı Gösterimi
        if parsed["fonksiyonlar"]:
            with st.expander(
                f"📌 {f.name} - Tespit Edilen İmar Fonksiyonları"
            ):
                st.dataframe(pd.DataFrame(parsed["fonksiyonlar"]))

        col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 2])
        ada = col1.text_input(f"Ada", value=parsed["ada"], key=f"ada_{idx}")
        parsel = col2.text_input(
            f"Parsel", value=parsed["parsel"], key=f"parsel_{idx}"
        )
        m2 = col3.number_input(f"m²", value=parsed["m2"], key=f"m2_{idx}")
        kaks_val = col4.number_input(
            f"Ağırlıklı KAKS",
            value=parsed["kaks"],
            key=f"kaks_{idx}",
            step=0.01,
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

if parsel_listesi:
    finansal_params = {
        "sabit_kaks_override": override_kaks,
        "sabit_kaks": sabit_kaks,
        "birim_konut_m2": 200,
    }
    sonuclar = hesapla_fizibilite(parsel_listesi, finansal_params)

    st.markdown("---")
    st.subheader("📊 İmar Hesaplama Sonuçları")
    st.dataframe(sonuclar["parsel_detaylari"], use_container_width=True)
    st.table(
        pd.DataFrame(
            list(sonuclar["ozet_imar"].items()), columns=["Metrik", "Değer"]
        )
    )
