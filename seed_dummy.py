from app import create_app
from app.extensions import db
from app.models import User, UserProgress
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()
app = create_app()

dummy_users = [
    {"nama": "Budi Santoso", "email": "budi@dummy.com", "points": 1250, "avatar": "👦"},
    {"nama": "Siti Aminah", "email": "siti@dummy.com", "points": 1800, "avatar": "👧"},
    {"nama": "Tono Keren", "email": "tono@dummy.com", "points": 850, "avatar": "🧒"},
    {"nama": "Rani Pintar", "email": "rani@dummy.com", "points": 2100, "avatar": "👩"},
    {"nama": "Andi Super", "email": "andi@dummy.com", "points": 1500, "avatar": "👨"},
    {"nama": "Dewi Cantik", "email": "dewi@dummy.com", "points": 950, "avatar": "👧"},
    {"nama": "Reza Kuat", "email": "reza@dummy.com", "points": 1100, "avatar": "👦"}
]

with app.app_context():
    print("Mulai menambahkan data dummy...")
    
    # Hapus dummy yang sudah ada (jika script dijalankan ulang)
    for data in dummy_users:
        user = User.query.filter_by(email=data['email']).first()
        if user:
            db.session.delete(user)
    db.session.commit()

    # Tambahkan dummy baru
    for data in dummy_users:
        hashed_password = generate_password_hash("password123")
        user = User(
            nama_lengkap=data['nama'],
            email=data['email'],
            password=hashed_password,
            is_verified=True,
            profile_pict=data['avatar']
        )
        db.session.add(user)
        db.session.commit() # commit agar user_id bisa didapat

        # Buat progress
        progress = UserProgress(
            user_id=user.id,
            total_points=data['points']
        )
        db.session.add(progress)
    
    db.session.commit()
    print("Data dummy berhasil ditambahkan!")
