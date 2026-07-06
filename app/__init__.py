import os
import datetime
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

    # Secret key untuk Flask session (admin dashboard)
    app.secret_key = os.getenv(
        "FLASK_SECRET_KEY", "admin_flask_secret_key_edutech_capstone_2026"
    )

    # Inisialisasi MongoDB
    init_mongo()

    # Auto-buat akun admin default jika belum ada
    _init_admin_user()

    # Daftarkan blueprint routes yang sudah ada (tidak diubah)
    from app.routes import main
    app.register_blueprint(main)

    # Daftarkan blueprint admin dashboard (baru)
    from app.admin.routes import admin as admin_bp
    app.register_blueprint(admin_bp, url_prefix="/admin")

    return app


def _init_admin_user():
    """
    Membuat akun admin default jika collection 'admins' masih kosong.
    Default: username=edutech, password=edutech2026 (di-hash dengan bcrypt).
    """
    try:
        import bcrypt
        from app.extensions import get_db

        db = get_db()
        admins_col = db["admins"]

        if admins_col.count_documents({}) == 0:
            default_password = "edutech2026"
            hashed = bcrypt.hashpw(
                default_password.encode("utf-8"), bcrypt.gensalt()
            )
            admins_col.insert_one({
                "username": "edutech",
                "password": hashed.decode("utf-8"),
                "role": "superadmin",
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            print("[Admin Init] ✅ Akun admin default berhasil dibuat.")
            print("[Admin Init]    Username: edutech | Password: edutech2026")
        else:
            print("[Admin Init] ✅ Koleksi admins sudah ada, skip inisialisasi.")
    except Exception as e:
        print(f"[Admin Init] ⚠️  Gagal membuat admin default: {e}")
