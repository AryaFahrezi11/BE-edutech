from app.extensions import db

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='siswa')

    # --- TAMBAHAN UNTUK OTP ---
    otp_code = db.Column(db.String(6), nullable=True)
    is_verified = db.Column(db.Boolean, default=False)

    # --- TAMBAHAN UNTUK PROFILE PICTURE ---
    # nullable=True karena saat baru daftar, user belum punya foto
    profile_pict = db.Column(db.String(255), nullable=True)

    # --- TAMBAHAN UNTUK TIMESTAMP ---
    # db.func.now() akan otomatis mengambil waktu server database
    created_at = db.Column(db.DateTime, default=db.func.now())
    # onupdate=db.func.now() akan otomatis memperbarui waktu setiap kali data user diubah
    updated_at = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())

    # Relasi 1-to-1 dengan UserProgress
    progress = db.relationship('UserProgress', backref='user', uselist=False, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "nama_lengkap": self.nama_lengkap,
            "email": self.email,
            "role": self.role,
            "is_verified": self.is_verified,
            "profile_pict": self.profile_pict,
            
            # Format objek DateTime menjadi String agar tidak error saat dikonversi ke JSON untuk Flutter
            "created_at": self.created_at.strftime("%Y-%m-%d %H:%M:%S") if self.created_at else None,
            "updated_at": self.updated_at.strftime("%Y-%m-%d %H:%M:%S") if self.updated_at else None
        }

class UserProgress(db.Model):
    __tablename__ = 'user_progress'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    
    # --- GAMIFIKASI & PROGRESS ---
    total_points = db.Column(db.Integer, default=0)
    streak_days = db.Column(db.Integer, default=0)
    last_login_date = db.Column(db.String(20), nullable=True)
    completed_items = db.Column(db.Text, default="[]") # Menyimpan JSON String
    
    unlocked_writing_letter = db.Column(db.Integer, default=0)
    unlocked_writing_word = db.Column(db.Integer, default=0)
    unlocked_spelling_letter = db.Column(db.Integer, default=0)
    unlocked_spelling_word = db.Column(db.Integer, default=0)

    # --- TAMBAHAN UNTUK MISSION MAP ---
    current_mission_index = db.Column(db.Integer, default=0)
    completed_missions = db.Column(db.Text, default="[]") # Menyimpan JSON list index

    def to_dict(self):
        import json
        try:
            items_list = json.loads(self.completed_items) if self.completed_items else []
        except:
            items_list = []
            
        try:
            missions_list = json.loads(self.completed_missions) if self.completed_missions else []
        except:
            missions_list = []

        return {
            "total_points": self.total_points,
            "streak_days": self.streak_days,
            "last_login_date": self.last_login_date,
            "completed_items": items_list,
            "unlocked_writing_letter": self.unlocked_writing_letter,
            "unlocked_writing_word": self.unlocked_writing_word,
            "unlocked_spelling_letter": self.unlocked_spelling_letter,
            "unlocked_spelling_word": self.unlocked_spelling_word,
            "current_mission_index": self.current_mission_index,
            "completed_missions": missions_list,
        }

class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    points_earned = db.Column(db.Integer, default=0)
    timestamp = db.Column(db.DateTime, default=db.func.now())

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "action": self.action,
            "description": self.description,
            "points_earned": self.points_earned,
            "timestamp": self.timestamp.strftime("%Y-%m-%d %H:%M:%S") if self.timestamp else None
        }