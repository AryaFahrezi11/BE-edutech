import os
import io
import json
import re
from flask import Blueprint, jsonify, request
from google import genai 
from google.genai import types
import PIL.Image
from werkzeug.security import generate_password_hash
from app.extensions import db # Import DB
from app.models import User # Import Model User

main = Blueprint('main', __name__)

# Inisialisasi client Gemini menggunakan API Key dari .env
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

# ... (endpoint / dan /api/login yang lama biarkan tetap aman) ...

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
            return jsonify({"status": "error", "message": "Email sudah terdaftar!"}), 409

        # 5. Hash Password demi keamanan
        hashed_password = generate_password_hash(password)

        # 6. Buat objek User baru dan simpan (Commit) ke MySQL
        user_baru = User(
            nama_lengkap=nama,
            email=email,
            password=hashed_password
        )
        db.session.add(user_baru)
        db.session.commit() # Menyimpan permanen ke MySQL

        return jsonify({
            "status": "success",
            "message": "Registrasi berhasil! Silakan login.",
            "data": user_baru.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback() # Batalkan jika ada error database
        return jsonify({"status": "error", "message": f"Gagal menyimpan data: {str(e)}"}), 500

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
        Tugasmu adalah memeriksa gambar tulisan tangan anak-anak pada aplikasi edukasi literasi bernama LITERA-DASH.
        
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