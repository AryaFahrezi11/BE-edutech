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
from pymongo import MongoClient


main = Blueprint('main', __name__)

# Inisialisasi client Gemini menggunakan API Key dari .env
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_KEY)

# --- KONFIGURASI EMAIL PENGIRIM ---
SENDER_EMAIL = os.getenv("SENDER_EMAIL") 
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# --- MONGODB ATLAS CONNECTION ---
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI) if MONGO_URI else None
mongo_db = mongo_client['edutech_db'] if mongo_client is not None else None
mongo_collection = mongo_db['writing_analytics'] if mongo_db is not None else None


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
    target_materi = request.form.get('target', 'A').strip()
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


@main.route('/api/sync-progress', methods=['POST'])
def sync_progress():
    from app.models import User, UserProgress # Import UserProgress
    data = request.get_json()
    email = data.get('email')
    
    if not email:
        return jsonify({"status": "error", "message": "Email diperlukan untuk sinkronisasi"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"status": "error", "message": "User tidak ditemukan"}), 404

    try:
        # Buat progress record jika belum ada
        if not user.progress:
            progress = UserProgress(user_id=user.id)
            db.session.add(progress)
            db.session.commit()
            
        progress = user.progress

        # Update fields jika ada di payload JSON
        if 'total_points' in data:
            progress.total_points = data['total_points']
        if 'streak_days' in data:
            progress.streak_days = data['streak_days']
        if 'last_login_date' in data:
            progress.last_login_date = data['last_login_date']
        if 'completed_items' in data:
            import json
            progress.completed_items = json.dumps(data['completed_items'])
        
        if 'unlocked_writing_letter' in data:
            progress.unlocked_writing_letter = data['unlocked_writing_letter']
        if 'unlocked_writing_lowercase' in data:
            progress.unlocked_writing_lowercase = data['unlocked_writing_lowercase']
        if 'unlocked_writing_word' in data:
            progress.unlocked_writing_word = data['unlocked_writing_word']
        if 'unlocked_spelling_letter' in data:
            progress.unlocked_spelling_letter = data['unlocked_spelling_letter']
        if 'unlocked_spelling_word' in data:
            progress.unlocked_spelling_word = data['unlocked_spelling_word']
            
        if 'current_mission_index' in data:
            progress.current_mission_index = data['current_mission_index']
        if 'completed_missions' in data:
            import json
            progress.completed_missions = json.dumps(data['completed_missions'])

        db.session.commit()
        
        return jsonify({
            "status": "success",
            "message": "Progress berhasil disinkronkan ke server",
            "progress": progress.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Gagal sinkronisasi: {str(e)}"}), 500

@main.route('/api/get-progress', methods=['GET'])
def get_progress():
    from app.models import User, UserProgress # Import UserProgress
    email = request.args.get('email')
    
    if not email:
        return jsonify({"status": "error", "message": "Email diperlukan"}), 400

    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({"status": "error", "message": "User tidak ditemukan"}), 404
        
    if not user.progress:
        # Jika belum ada progress, buatkan baru dengan nilai default 0
        progress = UserProgress(user_id=user.id)
        db.session.add(progress)
        db.session.commit()

    return jsonify({
        "status": "success",
        "progress": user.progress.to_dict()
    }), 200

@main.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    from app.models import User, UserProgress
    try:
        # Join User and UserProgress, order by total_points DESC
        leaderboard_data = db.session.query(User, UserProgress).join(
            UserProgress, User.id == UserProgress.user_id
        ).order_by(UserProgress.total_points.desc()).all()

        results = []
        for rank, (user, progress) in enumerate(leaderboard_data, start=1):
            emoji = user.profile_pict if user.profile_pict else "🧒"
            
            # Format skor agar ada titik ribuan (misal 1500 -> 1.500)
            score_formatted = f"{progress.total_points:,}".replace(',', '.')
            
            results.append({
                "rank": rank,
                "name": user.nama_lengkap,
                "score": score_formatted,
                "emoji": emoji,
                "email": user.email,
                "active": False # Akan diset di frontend
            })

        return jsonify({
            "status": "success",
            "leaderboard": results
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengambil leaderboard: {str(e)}"}), 500

@main.route('/api/activity/log', methods=['POST'])
def add_activity_log():
    from app.models import User, ActivityLog
    data = request.get_json()
    email = data.get('email')
    action = data.get('action')
    description = data.get('description', '')
    points = data.get('points', 0)

    if not email or not action:
        return jsonify({"status": "error", "message": "Email dan action wajib diisi!"}), 400

    try:
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        new_log = ActivityLog(
            user_id=user.id,
            action=action,
            description=description,
            points_earned=points
        )
        db.session.add(new_log)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Log aktivitas berhasil disimpan",
            "log": new_log.to_dict()
        }), 201

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Gagal menyimpan log: {str(e)}"}), 500

@main.route('/api/activity/logs', methods=['POST'])
def get_activity_logs():
    from app.models import User, ActivityLog
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"status": "error", "message": "Email wajib diisi!"}), 400

    try:
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        logs = ActivityLog.query.filter_by(user_id=user.id).order_by(ActivityLog.timestamp.desc()).limit(50).all()
        
        return jsonify({
            "status": "success",
            "logs": [log.to_dict() for log in logs]
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengambil logs: {str(e)}"}), 500

@main.route('/api/update-profile', methods=['POST'])
def update_profile():
    from app.models import User
    data = request.get_json()
    email = data.get('email')
    nama_lengkap = data.get('nama_lengkap')
    profile_pict = data.get('profile_pict')

    if not email:
        return jsonify({"status": "error", "message": "Email wajib diisi!"}), 400

    try:
        user = User.query.filter_by(email=email).first()
        if not user:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        if nama_lengkap:
            user.nama_lengkap = nama_lengkap
        if profile_pict:
            user.profile_pict = profile_pict

        db.session.commit()
        return jsonify({
            "status": "success",
            "message": "Profil berhasil diperbarui",
            "user": user.to_dict()
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": f"Gagal memperbarui profil: {str(e)}"}), 500

@main.route('/api/analytics', methods=['POST'])
def save_analytics():
    if mongo_collection is None:
        return jsonify({"error": "Koneksi MongoDB belum diatur di .env (MONGO_URI)"}), 500

    try:
        # 1. Tangkap JSON dari Flutter (Gemini Analytics)
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Tidak ada data JSON yang diterima"}), 400

        # 2. Opsional: Tambahkan waktu server
        data['server_timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 3. Simpan ke MongoDB Atlas
        mongo_collection.insert_one(data)
        
        # Hapus _id (ObjectId) sebelum dikembalikan sebagai response sukses (karena tidak bisa di-serialize)
        data.pop('_id', None)

        print("Berhasil menyimpan data analitik ke MongoDB!")
        return jsonify({
            "message": "Data berhasil disimpan ke Big Data",
            "data": data
        }), 201

    except Exception as e:
        print(f"Error saat menyimpan analytics: {e}")
        return jsonify({"error": str(e)}), 500

@main.route('/api/raport', methods=['GET'])
def get_raport():
    if mongo_collection is None:
        return jsonify({"error": "Koneksi MongoDB belum diatur di .env (MONGO_URI)"}), 500

    email = request.args.get('email')
    if not email:
        return jsonify({"status": "error", "message": "Email diperlukan"}), 400

    try:
        cursor = mongo_collection.find({"email": email})
        records = list(cursor)

        if not records:
            return jsonify({
                "status": "success",
                "data": {
                    "skills": [0, 0, 0, 0],
                    "ai_recommendation": "Halo Ayah/Bunda! Ananda belum mulai mengerjakan ujian menulis. Yuk, ajak Ananda untuk mulai berlatih sekarang! 🚀",
                    "strengths": [],
                    "weaknesses": []
                }
            }), 200

        total_accuracy = sum(r.get('accuracy_score', 0) for r in records)
        avg_accuracy = total_accuracy / len(records)

        wrong_letters_count = {}
        error_types_count = {}
        for r in records:
            # Hitung huruf salah dengan spesifik (kapital/kecil)
            wrongs = r.get('wrong_letters', [])
            for w in wrongs:
                if w:
                    if w.isupper():
                        w_str = f"kapital '{w}'"
                    else:
                        w_str = f"kecil '{w}'"
                    wrong_letters_count[w_str] = wrong_letters_count.get(w_str, 0) + 1
            
            # Hitung tipe kesalahan
            err_type = r.get('error_type')
            if err_type and err_type != "benar":
                error_types_count[err_type] = error_types_count.get(err_type, 0) + 1

        strengths = []
        weaknesses = []

        # Analisis Akurasi
        if avg_accuracy >= 80:
            strengths.append(f"Akurasi menulis sangat baik mencapai {avg_accuracy:.0f}%.")
        elif avg_accuracy >= 60:
            strengths.append(f"Akurasi menulis cukup baik ({avg_accuracy:.0f}%), namun masih bisa dimaksimalkan.")
        else:
            weaknesses.append(f"Akurasi menulis perlu ditingkatkan (saat ini {avg_accuracy:.0f}%).")

        # Analisis Huruf Tersulit
        most_wrong_letter = None
        if wrong_letters_count:
            most_wrong_letter = max(wrong_letters_count, key=wrong_letters_count.get)
            weaknesses.append(f"Sering terbalik/kesulitan saat menulis huruf {most_wrong_letter}.")
        
        # Analisis Tipe Kesalahan
        if error_types_count:
            most_common_error = max(error_types_count, key=error_types_count.get)
            formatted_error = most_common_error.replace('_', ' ')
            weaknesses.append(f"Tipe kesalahan dominan: {formatted_error}.")
        else:
            if avg_accuracy > 90:
                strengths.append("Hampir tidak ada kesalahan bentuk dalam penulisan.")

        # Pesan AI Executive Summary
        if most_wrong_letter:
            ai_recommendation = f"Halo Ayah/Bunda! Ananda menunjukkan semangat belajar yang tinggi. Saat ini, Ananda butuh sedikit bimbingan ekstra untuk melatih bentuk huruf {most_wrong_letter}. Yuk, temani Ananda berlatih menulis huruf tersebut di rumah!"
        elif avg_accuracy >= 80:
            ai_recommendation = "Halo Ayah/Bunda! Perkembangan belajar Ananda sungguh luar biasa! Keterampilan menulisnya sudah sangat rapi dan akurat. Terus berikan pujian untuk menjaga semangatnya ya!"
        else:
            ai_recommendation = "Halo Ayah/Bunda! Ananda sedang dalam tahap beradaptasi dengan bentuk huruf. Dampingi Ananda dan gunakan fitur 'Latihan Menulis' agar otot motoriknya semakin terbiasa."

        # Ekstrak data trend akurasi (maksimal 10 ujian terakhir)
        accuracy_trend = [r.get('accuracy_score', 0) for r in records[-10:]]

        return jsonify({
            "status": "success",
            "data": {
                # Urutan: Menulis, Mengeja, Observasi, Duel (Hanya fitur yang ada di app)
                "skills": [avg_accuracy, 75, 80, 85],
                "ai_recommendation": ai_recommendation,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "accuracy_trend": accuracy_trend
            }
        }), 200

    except Exception as e:
        print(f"Error saat mengambil raport: {e}")
        return jsonify({"error": str(e)}), 500