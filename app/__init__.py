from flask import Flask
from flask_cors import CORS

def create_app():
    # Inisialisasi aplikasi Flask
    app = Flask(__name__)
    
    # Buka akses CORS untuk semua domain (penting untuk Flutter)
    CORS(app) 

    # Daftarkan rute/endpoint dari routes.py
    from .routes import main
    app.register_blueprint(main)

    return app