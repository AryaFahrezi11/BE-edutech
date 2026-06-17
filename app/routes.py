import os
import io
import json
import re
import jwt
import datetime
from flask import Blueprint, jsonify, request
from google import genai 
from google.genai import types
import PIL.Image
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db # Import DB
from app.models import User # Import Model User
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


main = Blueprint('main', __name__)

# Inisialisasi client Gemini menggunakan API Key dari .env
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

# --- KONFIGURASI EMAIL PENGIRIM ---
SENDER_EMAIL = os.getenv("SENDER_EMAIL") 
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")


@main.route('/api/login', methods=['POST'])
def login_user():
    data = request.get_json()

    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"status": "error", "message": "Email dan Password wajib diisi!"}), 400

    email = data['email'].strip().lower()
    password = data['password']

    # 1. Cari user di database
    user = User.query.filter_by(email=email).first()

    # 2. Cek apakah user ada dan passwordnya cocok
    if not user or not check_password_hash(user.password, password):
        return jsonify({"status": "error", "message": "Email atau Password salah!"}), 401

    # --- TAMBAHAN BARU: Validasi Status Verifikasi OTP ---
    if not user.is_verified:
        return jsonify({
            "status": "unverified", # Status khusus untuk ditangkap oleh Flutter
            "message": "Akun kamu belum diverifikasi! Yuk masukkan Kode Rahasia yang dikirim ke emailmu.",
            "email": user.email # Berguna agar Flutter bisa langsung membawa email ini ke halaman OTP
        }), 403 # Menggunakan kode 403 (Forbidden) karena akses ditolak

    try:
        # 3. Buat JWT Token
        secret_key = os.getenv("JWT_SECRET_KEY", "fallback_rahasia_edutech")
        payload = {
            'user_id': user.id,
            'email': user.email,
            'role': user.role,
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        }
        token = jwt.encode(payload, secret_key, algorithm='HS256')

        # 4. Kirim token ke Flutter
        return jsonify({
            "status": "success",
            "message": f"Selamat datang kembali, {user.nama_lengkap}!",
            "token": token,
            "user": user.to_dict()
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal login: {str(e)}"}), 500

@main.route('/api/register', methods=['POST'])
def register_user():
    data = request.get_json()

    # 1. Validasi Input Kosong
    if not data or not all(k in data for k in ('nama_lengkap', 'email', 'password', 'konfirmasi_password')):
        return jsonify({"status": "error", "message": "Semua kolom wajib diisi!"}), 400

    nama = data['nama_lengkap'].strip()
    email = data['email'].strip().lower()
    password = data['password']
    konfirmasi_password = data['konfirmasi_password']

    if not nama or not email or not password:
        return jsonify({"status": "error", "message": "Data tidak boleh kosong!"}), 400

    # 2. Validasi Format Email
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"status": "error", "message": "Format email tidak valid!"}), 400

    # 3. Validasi Kecocokan Password
    if password != konfirmasi_password:
        return jsonify({"status": "error", "message": "Password dan Konfirmasi Password tidak cocok!"}), 400
    
    if len(password) < 6:
        return jsonify({"status": "error", "message": "Password minimal 6 karakter!"}), 400

    try:
        # 4. Cek apakah email sudah terdaftar di database MySQL
        user_exist = User.query.filter_by(email=email).first()
        if user_exist:
            # Jika user ada tapi belum verifikasi, kita bisa beri pesan khusus (Opsional)
            if not user_exist.is_verified:
                return jsonify({"status": "error", "message": "Email sudah terdaftar tapi belum diverifikasi. Silakan cek email untuk OTP."}), 409
            return jsonify({"status": "error", "message": "Email sudah terdaftar!"}), 409

        # 5. Hash Password demi keamanan
        hashed_password = generate_password_hash(password)

        # 6. Generate 6 Digit OTP
        kode_otp = str(random.randint(100000, 999999))

        # 7. Buat objek User baru (is_verified = False)
        user_baru = User(
            nama_lengkap=nama,
            email=email,
            password=hashed_password,
            otp_code=kode_otp,
            is_verified=False
        )
        db.session.add(user_baru)
        db.session.commit() # Menyimpan permanen ke MySQL

        # 8. Proses Kirim Email OTP
        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = email
        msg['Subject'] = "Kode OTP Edutech Kamu! 🚀"
        
        body = f"""
        Halo {nama}! 👋
        
        Pendaftaran kamu hampir selesai.
        Gunakan 6 digit Kode Rahasia di bawah ini untuk memverifikasi akun kamu:
        
        {kode_otp}
        
        Ayo mulai petualangan belajarmu! Jangan berikan kode ini ke siapapun ya.
        """
        msg.attach(MIMEText(body, 'plain'))

        # Mengirim email menggunakan server Gmail
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        return jsonify({
            "status": "success",
            "message": "Hore! Akun berhasil dibuat. Cek email kamu untuk melihat Kode Rahasia!",
            "email": email # Dikirim balik agar Flutter tahu email siapa yang sedang diverifikasi
        }), 201

    except Exception as e:
        db.session.rollback() # Batalkan jika ada error database atau gagal kirim email
        return jsonify({"status": "error", "message": f"Gagal memproses pendaftaran: {str(e)}"}), 500


@main.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp_input = data.get('otp')

    if not email or not otp_input:
        return jsonify({"status": "error", "message": "Email dan OTP wajib diisi!"}), 400

    try:
        # Cari user berdasarkan email
        user = User.query.filter_by(email=email).first()

        if not user:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        if user.is_verified:
            return jsonify({"status": "error", "message": "Akun ini sudah diverifikasi sebelumnya!"}), 400

        # Cocokkan OTP
        if user.otp_code == otp_input:
            user.is_verified = True
            user.otp_code = None # Hapus OTP karena sudah terpakai
            db.session.commit()
            return jsonify({"status": "success", "message": "Yey! Verifikasi berhasil. Silakan Login!"}), 200
        else:
            return jsonify({"status": "error", "message": "Kode rahasia salah, coba lagi ya!"}), 400

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Gagal memverifikasi: {str(e)}"}), 500

@main.route('/api/ujian-menulis-gemini', methods=['POST'])
def ujian_menulis_gemini():
    if 'gambar' not in request.files:
        return jsonify({"status": "error", "message": "File gambar tidak ditemukan!"}), 400
    
    file_gambar = request.files['gambar']
    target_materi = request.form.get('target', 'A').upper().strip()
    kategori = request.form.get('kategori', 'huruf')

    try:
        # Konversi gambar biner ke PIL Image
        img_bytes = file_gambar.read()
        img = PIL.Image.open(io.BytesIO(img_bytes))

        # Rancang Prompt untuk Gemini
        prompt = f"""
        Kamu adalah seorang guru Sekolah Dasar (SD) yang sangat ramah, penyabar, dan suportif.
        Tugasmu adalah memeriksa gambar tulisan tangan anak-anak pada aplikasi edukasi literasi bernama Edutech.
        
        Anak ini ditugaskan untuk menulis {kategori}: "{target_materi}".
        Periksa gambar yang dilampirkan dengan saksama:
        1. Apakah tulisan tersebut sudah terbaca jelas sebagai "{target_materi}"?
        2. Berikan skor dari 0 sampai 100.
        3. Berikan jumlah bintang (0 sampai 3) berdasarkan kualitas tulisan.
        4. Berikan umpan balik (pesan) motivasi yang singkat, ceria, dan membangun dalam bahasa Indonesia.

        PENTING: Kamu HANYA boleh merespons dalam format JSON mentah tanpa menggunakan format markdown seperti ```json atau teks tambahan lainnya di luar kurung kurawal. 

        Struktur JSON harus persis seperti ini:
        {{
            "skor": 85,
            "bintang": 3,
            "lulus": true,
            "pesan": "Teks pesan motivasimu di sini"
        }}
        """

        # --- PERUBAHAN UNTUK SDK BARU ---
        # Menggunakan client.models.generate_content dan model gemini-2.5-flash yang super cepat
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img]
        )
        
        # --- PERBAIKAN CLEANSING TEKS GEMINI ---
        clean_text = response.text.strip()
        
        # Bersihkan semua kemungkinan tag markdown yang merusak json.loads
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].strip()
            
        # Cari kurung kurawal pertama dan terakhir untuk memastikan hanya mengambil objek JSON
        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}") + 1
        if start_idx != -1 and end_idx != -1:
            clean_text = clean_text[start_idx:end_idx]

        hasil_json = json.loads(clean_text)
        return jsonify({
            "status": "success",
            "hasil_analisis": hasil_json
        }), 200

    except json.JSONDecodeError:
        return jsonify({
            "status": "error", 
            "message": "Gemini gagal mengembalikan format data yang sesuai.",
            "raw_response": response.text
        }), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Terjadi kesalahan pada server: {str(e)}"}), 500