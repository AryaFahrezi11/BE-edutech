import os
from flask import Flask
from flask_cors import CORS

from app.extensions import init_mongo


def create_app():
    app = Flask(__name__)
    CORS(app)

    # Pastikan .env ter-load saat app factory dipanggil
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass

    # Inisialisasi MongoDB
    init_mongo()

    # Daftarkan blueprint routes kamu
    from app.routes import main
    app.register_blueprint(main)

    return app
