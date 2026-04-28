# ═══════════════════════════════════════════════════════
# Plesk + Python (Passenger WSGI) Kurulum Rehberi
# Tescil Bildirimi Web Uygulaması
# ═══════════════════════════════════════════════════════

## 1. PLESK PANELİNDE PYTHON AYARI

Plesk → Websites & Domains → Alan adınız
→ "Python" simgesine tıklayın

  Python version    : 3.10 (veya 3.11)
  Application root  : /httpdocs/tescil          ← klasör adı
  Application URL   : /tescil                   ← URL yolu
  Application mode  : production
  Startup file      : passenger_wsgi.py          ← aşağıda oluşturulacak

→ "Apply" / "OK" butonuna basın.


## 2. DOSYALARI YÜKLE

FTP veya Plesk File Manager ile şu yapıyı oluşturun:

  httpdocs/
  └── tescil/
      ├── passenger_wsgi.py      ← bu rehberin yanındaki dosya
      ├── app.py
      ├── dxf_processor.py
      ├── requirements.txt
      └── templates/
          └── index.html


## 3. BAĞIMLILIKLARI KURUN

Plesk → Websites & Domains → Alan adınız → Python
→ "Install requirements" butonuna tıklayın
(requirements.txt otomatik okunur)

Veya SSH ile:
  cd ~/httpdocs/tescil
  pip install -r requirements.txt --target ./vendor


## 4. UYGULAMAYI BAŞLATIN

Plesk Python panelinde → "Restart" butonuna basın.

Test: https://alanadi.com/tescil


## 5. SORUN GİDERME

Hata varsa:
  Plesk → Logs → Error log (Apache/Nginx)
  
  Veya SSH:
  tail -f /var/www/vhosts/alanadi.com/logs/error_log
