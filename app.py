import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

class GayrimenkulOtomasyonu:
    def __init__(self, mahalle, ada, parsel, tapu_alani, nitelik, terk_yapildi_mi, kaks, taks, sunum_tipi):
        self.mahalle = mahalle
        self.ada = ada
        self.parsel = parsel
        self.tapu_alani = float(tapu_alani)
        self.nitelik = nitelik
        self.terk_yapildi_mi = terk_yapildi_mi  # True: Terk Yapılmış (Arsa), False: Terk Yapılmamış (Bahçe)
        self.kaks = float(kaks)
        self.taks = float(taks)
        self.sunum_tipi = sunum_tipi  # "Kat Karşılığı" veya "Satılık"
        
        self.hesapla()

    def hesapla(self):
        # Terk durumuna göre kesinti ve alan hesaplama
        if self.terk_yapildi_mi or self.nitelik.lower() == 'arsa':
            self.terk_durumu_str = "18. Madde Uygulanmış (Terk Yapılmış)"
            self.kesinti_orani = 0.00
            self.net_alan = self.tapu_alani
        else:
            self.terk_durumu_str = "18. Madde Dışında (Terk Yapılmamış)"
            self.kesinti_orani = 0.30
            self.net_alan = self.tapu_alani * 0.70

        self.net_emsal_alani = self.net_alan * self.kaks
        self.ilave_alan = self.net_emsal_alani * 0.30
        self.toplam_brut_insaat = self.net_emsal_alani * 1.30
        self.max_taban_alani = self.net_alan * self.taks

    def pdf_rapor_olustur(self, dosya_adi="Imar_Analiz_Raporu.pdf"):
        doc = SimpleDocTemplate(dosya_adi, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        story = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'TitleStyle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1A2B4C'),
            alignment=1,
            spaceAfter=10
        )
        
        subtitle_style = ParagraphStyle(
            'SubTitleStyle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=colors.HexColor('#555555'),
            alignment=1,
            spaceAfter=15
        )

        # Kurumsal Başlık
        story.append(Paragraph("<b>1st ESTATE - MERİÇ GAYRİMENKUL DANIŞMANLIK</b>", title_style))
        story.append(Paragraph(f"<b>İMAR EMSAL & ANALİZ RAPORU ({self.sunum_tipi.upper()})</b>", subtitle_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#1A2B4C'), spaceAfter=15))

        # Taşınmaz Bilgileri Tablosu
        data_tasinmaz = [
            ["Mahalle / İlçe", f"{self.mahalle} / Beykoz", "Nitelik", self.nitelik],
            ["Ada / Parsel", f"{self.ada} / {self.parsel}", "18. Madde / Terk Durumu", self.terk_durumu_str],
            ["Tapu Alanı", f"{self.tapu_alani:,.2f} m²", "Sunum Modeli", self.sunum_tipi]
        ]
        
        t1 = Table(data_tasinmaz, colWidths=[110, 160, 130, 140])
        t1.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#F8F9FA')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TEXTCOLOR', (0,0), (-1,-1), colors.HexColor('#333333')),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t1)
        story.append(Spacer(1, 15))

        # İmar ve Hesaplama Sonuçları Tablosu
        data_hesap = [
            ["Girdi / Hesap Kalemi", "Değer / Ölçü"],
            ["Hesaba Esas Net Alan", f"{self.net_alan:,.2f} m² (%{int((1-self.kesinti_orani)*100)} esas)"],
            ["Uygulanan Emsal (KAKS)", f"{self.kaks:.2f}"],
            ["Net Emsal İnşaat Alanı", f"{self.net_emsal_alani:,.2f} m²"],
            ["%30 İlave Alan (Emsal Harici)", f"{self.ilave_alan:,.2f} m²"],
            ["TOPLAM BRÜT İNŞAAT ALANI", f"{self.toplam_brut_insaat:,.2f} m²"],
            ["Max Taban Alanı (TAKS - 0.30)", f"{self.max_taban_alani:,.2f} m²"]
        ]

        t2 = Table(data_hesap, colWidths=[270, 270])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (1,0), colors.HexColor('#1A2B4C')),
            ('TEXTCOLOR', (0,0), (1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#CCCCCC')),
            ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
            ('FONTNAME', (0,5), (1,5), 'Helvetica-Bold'),
            ('BACKGROUND', (0,5), (1,5), colors.HexColor('#E2E8F0')),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('PADDING', (0,0), (-1,-1), 6),
        ]))
        story.append(t2)
        story.append(Spacer(1, 15))

        # Sunum Tipine Göre Süreç Akışı
        if self.sunum_tipi == "Kat Karşılığı":
            surec = "Süreç Akışı: Arsa Analizi ➔ Projelendirme ➔ Sözleşme ➔ Ruhsat ➔ İnşaat ➔ Teslim"
        else:
            surec = "Süreç Akışı: Arsa Analizi ➔ Terk İşlemi ➔ Projelendirme ➔ Ruhsat ➔ İnşaat ➔ İskan"
            
        story.append(Paragraph(f"<b>{surec}</b>", styles['Normal']))
        story.append(Spacer(1, 15))

        # İletişim Bilgileri (Kurumsal Altbilgi)
        iletisim_text = "<b>Gayrimenkul Danışmanı:</b> Umutcan K. MERİÇ (0539 451 61 61) | Süleyman MERİÇ (0532 695 10 83)<br/>" \
                        "<b>Adres:</b> Çiftlik Mah. Çavuşbaşı Cumhuriyet Cad. No:171/3 Beykoz/İSTANBUL"
        story.append(Paragraph(iletisim_text, styles['Normal']))

        doc.build(story)
        print(f"Rapor oluşturuldu: {dosya_adi}")

# Örnek Kullanım:
# Terk Yapılmamış Bahçe Niteliğinde Parsel (Müteahhit Sunumu)
p1 = GayrimenkulOtomasyonu("Yavuzselim", "1647", "10", 6398.86, "Bahçe", terk_yapildi_mi=False, kaks=0.40, taks=0.30, sunum_tipi="Kat Karşılığı")
p1.pdf_rapor_olustur("Yavuzselim_1647_10_Rapor.pdf")

# Terk Yapılmış Arsa Niteliğinde Parsel (Satılık Müşteri Sunumu)
p2 = GayrimenkulOtomasyonu("Fatih", "40", "70", 1372.10, "Arsa", terk_yapildi_mi=True, kaks=0.40, taks=0.30, sunum_tipi="Satılık")
p2.pdf_rapor_olustur("Fatih_40_70_Rapor.pdf")
