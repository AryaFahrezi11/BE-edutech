import os
from dotenv import load_dotenv
load_dotenv()

from werkzeug.security import generate_password_hash
from app import create_app
from app.extensions import db
from app.models import User, UserProgress

app = create_app()

dummy_users = [
    {"email": "budi@dummy.com", "name": "Budi", "score": 1500},
    {"email": "siti@dummy.com", "name": "Siti", "score": 1200},
    {"email": "andi@dummy.com", "name": "Andi", "score": 850},
    {"email": "rara@dummy.com", "name": "Rara", "score": 400},
    {"email": "doni@dummy.com", "name": "Doni", "score": 250},
    {"email": "maya@dummy.com", "name": "Maya", "score": 100},
]

with app.app_context():
    for dummy in dummy_users:
        # Cek apakah user sudah ada
        user = User.query.filter_by(email=dummy["email"]).first()
        if not user:
            # Create user
            user = User(
                nama_lengkap=dummy["name"],
                email=dummy["email"],
                password=generate_password_hash("dummy123"),
                is_verified=True,
                role="dummy"
            )
            db.session.add(user)
            db.session.commit()
            
            # Create progress
            progress = UserProgress(
                user_id=user.id,
                total_points=dummy["score"]
            )
            db.session.add(progress)
            db.session.commit()
            print(f"Inserted {dummy['name']} with {dummy['score']} points.")
        else:
            # Update score if user exists
            progress = UserProgress.query.filter_by(user_id=user.id).first()
            if progress:
                progress.total_points = dummy["score"]
                db.session.commit()
            print(f"Updated {dummy['name']} with {dummy['score']} points.")

    print("Dummy data successfully populated!")
