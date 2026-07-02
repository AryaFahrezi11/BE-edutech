import os
from flask import Flask
from app.extensions import db # Import db dari extensions
from flask_cors import CORS

def create_app():
    app = Flask(__name__)
    CORS(app)  # Aktifkan CORS untuk semua rute

    # Pastikan .env ter-load saat app factory dipanggil
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    # Konfigurasi Database dari .env
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Inisialisasi database dengan app Flask
    db.init_app(app)
    
    # Daftarkan blueprint routes kamu
    from app.routes import main
    app.register_blueprint(main)
    
    # Membuat tabel secara otomatis jika belum ada di phpMyAdmin
    with app.app_context():
        db.create_all()
        
    return app