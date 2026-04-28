"""
Plesk Python (Passenger WSGI) giriş noktası.
Bu dosya httpdocs/tescil/ klasörüne yerleştirilmeli.
Plesk Python panelinde "Startup file" olarak passenger_wsgi.py girilmeli.
"""

import sys
import os

# Uygulama klasörünü Python path'ine ekle
INTERP = os.path.join(os.path.dirname(__file__), 'venv', 'bin', 'python3')
if sys.executable != INTERP:
    os.execl(INTERP, INTERP, *sys.argv)

# vendor klasörü (pip install --target ile kurulduysa)
vendor_path = os.path.join(os.path.dirname(__file__), 'vendor')
if os.path.isdir(vendor_path) and vendor_path not in sys.path:
    sys.path.insert(0, vendor_path)

sys.path.insert(0, os.path.dirname(__file__))

from app import app as application
