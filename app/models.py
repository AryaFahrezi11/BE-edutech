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
            
            # PENTING: password dan otp_code TIDAK dimasukkan ke sini agar tidak bocor ke frontend!
        }