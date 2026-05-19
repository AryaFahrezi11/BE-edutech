from app.extensions import db

class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    nama_lengkap = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='siswa')

    def to_dict(self):
        return {
            "id": self.id,
            "nama_lengkap": self.nama_lengkap,
            "email": self.email,
            "role": self.role
        }