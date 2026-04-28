# Tescil Bildirimi Web Uygulaması

Kadastro ayırma işlemi için otomatik tescil bildirimi oluşturucu.

## Kurulum

```bash
pip install -r requirements.txt
python app.py
```

Tarayıcıda açın: http://localhost:5000

## Kullanım

1. **Çizim DXF** ve **Tescil Bildirimi Şablonu DXF** yükleyin
2. **Çizimi Analiz Et** butonuna tıklayın → parsel alanları otomatik hesaplanır
3. İl, İlçe, Köy, Malik vb. bilgileri girin
4. **DXF Oluştur & İndir** butonuyla dosyayı indirin

## Dosya Yapısı

```
tescil_app/
├── app.py              # Flask uygulaması
├── dxf_processor.py    # DXF işleme motoru
├── requirements.txt    # Python bağımlılıkları
├── templates/
│   └── index.html      # Web arayüzü
└── README.md
```

## Web Sunucusuna Kurulum (Nginx + Gunicorn)

```bash
pip install gunicorn
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

Nginx yapılandırması için `proxy_pass http://localhost:5000` kullanın.
