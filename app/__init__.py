import os
from flask import Flask
from app.extensions import db # Import db dari extensions

def create_app():
    app = Flask(__name__)
    
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