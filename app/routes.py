import os
import io
import json
import re
import jwt
import datetime
from flask import Blueprint, jsonify, request, render_template
from google import genai
from google.genai import types
import PIL.Image
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db  # MongoDB handle
from app.models import User, UserProgress, ActivityLog
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


main = Blueprint('main', __name__)


# --- KONFIGURASI EMAIL PENGIRIM ---
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# --- MONGODB COLLECTION ---
# writing_analytics menggunakan db dari app.extensions
def get_analytics_collection():
    return db['writing_analytics']

def _now_ts_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _ensure_defaults_user_doc(doc: dict) -> dict:
    if not doc:
        return None
    d = dict(doc)
    if "id" not in d:
        d["id"] = d.get("_id")
    return d


def _get_next_counter_seq(counter_name: str) -> int:
    counter = db["counters"].find_one_and_update(
        {"name": counter_name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
    )
    return int(counter.get("seq", 0))


@main.route('/')
def landing_page():
    """Landing page — mengenalkan aplikasi EduTech"""
    return render_template('landing.html')


@main.route('/api/login', methods=['POST'])
def login_user():
    data = request.get_json()

    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"status": "error", "message": "Email dan Password wajib diisi!"}), 400

    email = data['email'].strip().lower()
    password = data['password']

    users_col = db[User.COLLECTION]
    user_doc = users_col.find_one({"email": email})
    user_doc = _ensure_defaults_user_doc(user_doc)

    if not user_doc:
        return jsonify({
            "status": "unregistered", 
            "message": "Akun kamu belum terdaftar nih! Yuk buat akun baru dulu."
        }), 404

    if not check_password_hash(user_doc.get("password"), password):
        return jsonify({"status": "error", "message": "Email atau Password salah!"}), 401

    if not user_doc.get("is_verified", False):
        return jsonify({
            "status": "unverified",
            "message": "Akun kamu belum diverifikasi! Yuk masukkan Kode Rahasia yang dikirim ke emailmu.",
            "email": user_doc.get("email")
        }), 403

    try:
        secret_key = os.getenv("JWT_SECRET_KEY", "fallback_rahasia_edutech")
        payload = {
            'user_id': user_doc.get('id'),
            'email': user_doc.get('email'),
            'role': user_doc.get('role'),
            'exp': datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=24)
        }
        token = jwt.encode(payload, secret_key, algorithm='HS256')

        return jsonify({
            "status": "success",
            "message": f"Selamat datang kembali, {user_doc.get('nama_lengkap')}!",
            "token": token,
            "user": User.to_dict(user_doc)
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal login: {str(e)}"}), 500


@main.route('/api/register', methods=['POST'])
def register_user():
    data = request.get_json()

    if not data or not all(k in data for k in ('nama_lengkap', 'email', 'password', 'konfirmasi_password')):
        return jsonify({"status": "error", "message": "Semua kolom wajib diisi!"}), 400

    nama = data['nama_lengkap'].strip()
    email = data['email'].strip().lower()
    password = data['password']
    konfirmasi_password = data['konfirmasi_password']

    if not nama or not email or not password:
        return jsonify({"status": "error", "message": "Data tidak boleh kosong!"}), 400

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"status": "error", "message": "Format email tidak valid!"}), 400

    if password != konfirmasi_password:
        return jsonify({"status": "error", "message": "Password dan Konfirmasi Password tidak cocok!"}), 400

    if len(password) < 6:
        return jsonify({"status": "error", "message": "Password minimal 6 karakter!"}), 400

    try:
        users_col = db[User.COLLECTION]

        user_exist = users_col.find_one({"email": email})
        if user_exist:
            if not user_exist.get('is_verified', False):
                return jsonify({"status": "error", "message": "Email sudah terdaftar tapi belum diverifikasi. Silakan cek email untuk OTP."}), 409
            return jsonify({"status": "error", "message": "Email sudah terdaftar!"}), 409

        hashed_password = generate_password_hash(password)
        kode_otp = str(random.randint(100000, 999999))

        user_id = _get_next_counter_seq('users')
        now_str = _now_ts_str()

        user_doc = {
            "id": user_id,
            "nama_lengkap": nama,
            "email": email,
            "password": hashed_password,
            "role": "siswa",
            "otp_code": kode_otp,
            "is_verified": False,
            "profile_pict": None,
            "created_at": now_str,
            "updated_at": now_str,
        }

        users_col.insert_one(user_doc)

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

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        return jsonify({
            "status": "success",
            "message": "Hore! Akun berhasil dibuat. Cek email kamu untuk melihat Kode Rahasia!",
            "email": email
        }), 201

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal memproses pendaftaran: {str(e)}"}), 500


@main.route('/api/verify-otp', methods=['POST'])
def verify_otp():
    data = request.get_json()
    email = data.get('email')
    otp_input = data.get('otp')

    if not email or not otp_input:
        return jsonify({"status": "error", "message": "Email dan OTP wajib diisi!"}), 400

    try:
        users_col = db[User.COLLECTION]
        user_doc = users_col.find_one({"email": email})
        user_doc = _ensure_defaults_user_doc(user_doc)

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        if user_doc.get('is_verified', False):
            return jsonify({"status": "error", "message": "Akun ini sudah diverifikasi sebelumnya!"}), 400

        if user_doc.get('otp_code') == otp_input:
            users_col.update_one(
                {"_id": user_doc.get("_id")},
                {"$set": {"is_verified": True, "otp_code": None, "updated_at": _now_ts_str()}},
            )
            return jsonify({"status": "success", "message": "Yey! Verifikasi berhasil. Silakan Login!"}), 200

        return jsonify({"status": "error", "message": "Kode rahasia salah, coba lagi ya!"}), 400

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal memverifikasi: {str(e)}"}), 500


@main.route('/api/forgot-password', methods=['POST'])
def forgot_password():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"status": "error", "message": "Email wajib diisi!"}), 400

    try:
        users_col = db[User.COLLECTION]
        user_doc = users_col.find_one({"email": email.strip().lower()})

        if not user_doc:
            return jsonify({"status": "error", "message": "Email tidak terdaftar!"}), 404

        kode_otp = str(random.randint(100000, 999999))
        
        users_col.update_one(
            {"_id": user_doc.get("_id")},
            {"$set": {"reset_otp": kode_otp, "updated_at": _now_ts_str()}}
        )

        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = email
        msg['Subject'] = "Reset Password Edutech Kamu! 🔑"

        body = f"""
        Halo {user_doc.get('nama_lengkap', 'Petualang')}! 👋

        Kami menerima permintaan untuk mereset password akun Edutech kamu.
        Gunakan 6 digit Kode Rahasia di bawah ini untuk mereset password:

        {kode_otp}

        Jika kamu tidak meminta reset password, abaikan saja email ini.
        Jangan berikan kode ini ke siapapun ya.
        """
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        return jsonify({"status": "success", "message": "Kode OTP reset password telah dikirim ke email kamu."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengirim email reset: {str(e)}"}), 500


@main.route('/api/reset-password', methods=['POST'])
def reset_password():
    data = request.get_json()
    email = data.get('email')
    otp_input = data.get('otp')
    new_password = data.get('new_password')
    konfirmasi = data.get('konfirmasi_password')

    if not all([email, otp_input, new_password, konfirmasi]):
        return jsonify({"status": "error", "message": "Semua kolom wajib diisi!"}), 400
        
    if new_password != konfirmasi:
        return jsonify({"status": "error", "message": "Password baru dan konfirmasi tidak cocok!"}), 400
        
    if len(new_password) < 6:
        return jsonify({"status": "error", "message": "Password minimal 6 karakter!"}), 400

    try:
        users_col = db[User.COLLECTION]
        user_doc = users_col.find_one({"email": email.strip().lower()})

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        if user_doc.get('reset_otp') != otp_input:
            return jsonify({"status": "error", "message": "Kode rahasia salah, coba lagi ya!"}), 400

        hashed_password = generate_password_hash(new_password)
        
        users_col.update_one(
            {"_id": user_doc.get("_id")},
            {"$set": {"password": hashed_password, "reset_otp": None, "updated_at": _now_ts_str()}}
        )

        return jsonify({"status": "success", "message": "Hore! Password berhasil diubah. Silakan Login dengan password baru."}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mereset password: {str(e)}"}), 500


@main.route('/api/sync-progress', methods=['POST'])
def sync_progress():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"status": "error", "message": "Email diperlukan untuk sinkronisasi"}), 400

    try:
        users_col = db[User.COLLECTION]
        progress_col = db[UserProgress.COLLECTION]

        user_doc = users_col.find_one({"email": email})
        user_doc = _ensure_defaults_user_doc(user_doc)

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan"}), 404

        user_id = user_doc.get('id')

        progress_doc = progress_col.find_one({"user_id": user_id})
        if not progress_doc:
            new_id = _get_next_counter_seq('user_progress')
            base = {
                "id": new_id,
                "user_id": user_id,
                "total_points": 0,
                "streak_days": 0,
                "last_login_date": None,
                "completed_items": json.dumps([]),
                "unlocked_writing_letter": 0,
                "unlocked_writing_lowercase": 0,
                "unlocked_writing_word": 0,
                "unlocked_spelling_letter": 0,
                "unlocked_spelling_word": 0,
                "unlocked_spelling_exam_letter": 0,
                "unlocked_spelling_exam_word": 0,
                "unlocked_writing_exam_letter": 0,
                "unlocked_writing_exam_lowercase": 0,
                "unlocked_writing_exam_word": 0,
                "current_mission_index": 0,
                "completed_missions": json.dumps([]),
                "completed_hunt_items": json.dumps([]),
            }
            progress_col.insert_one(base)
            progress_doc = base

        update_fields = {}
        if 'total_points' in data:
            update_fields['total_points'] = data['total_points']
        if 'streak_days' in data:
            update_fields['streak_days'] = data['streak_days']
        if 'last_login_date' in data:
            update_fields['last_login_date'] = data['last_login_date']
        if 'completed_items' in data:
            update_fields['completed_items'] = json.dumps(data['completed_items'])

        if 'unlocked_writing_letter' in data:
            update_fields['unlocked_writing_letter'] = data['unlocked_writing_letter']
        if 'unlocked_writing_lowercase' in data:
            update_fields['unlocked_writing_lowercase'] = data['unlocked_writing_lowercase']
        if 'unlocked_writing_word' in data:
            update_fields['unlocked_writing_word'] = data['unlocked_writing_word']
        if 'unlocked_spelling_letter' in data:
            update_fields['unlocked_spelling_letter'] = data['unlocked_spelling_letter']
        if 'unlocked_spelling_word' in data:
            update_fields['unlocked_spelling_word'] = data['unlocked_spelling_word']
        if 'unlocked_spelling_exam_letter' in data:
            update_fields['unlocked_spelling_exam_letter'] = data['unlocked_spelling_exam_letter']
        if 'unlocked_spelling_exam_word' in data:
            update_fields['unlocked_spelling_exam_word'] = data['unlocked_spelling_exam_word']
        if 'unlocked_writing_exam_letter' in data:
            update_fields['unlocked_writing_exam_letter'] = data['unlocked_writing_exam_letter']
        if 'unlocked_writing_exam_lowercase' in data:
            update_fields['unlocked_writing_exam_lowercase'] = data['unlocked_writing_exam_lowercase']
        if 'unlocked_writing_exam_word' in data:
            update_fields['unlocked_writing_exam_word'] = data['unlocked_writing_exam_word']

        if 'current_mission_index' in data:
            update_fields['current_mission_index'] = data['current_mission_index']
        if 'completed_missions' in data:
            update_fields['completed_missions'] = json.dumps(data['completed_missions'])
        if 'completed_hunt_items' in data:
            update_fields['completed_hunt_items'] = json.dumps(data['completed_hunt_items'])

        if update_fields:
            progress_col.update_one({"user_id": user_id}, {"$set": update_fields})

        progress_doc = progress_col.find_one({"user_id": user_id})

        return jsonify({
            "status": "success",
            "message": "Progress berhasil disinkronkan ke server",
            "progress": UserProgress.to_dict(progress_doc)
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal sinkronisasi: {str(e)}"}), 500


@main.route('/api/get-progress', methods=['GET'])
def get_progress():
    email = request.args.get('email')

    if not email:
        return jsonify({"status": "error", "message": "Email diperlukan"}), 400

    try:
        users_col = db[User.COLLECTION]
        progress_col = db[UserProgress.COLLECTION]

        user_doc = users_col.find_one({"email": email})
        user_doc = _ensure_defaults_user_doc(user_doc)

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan"}), 404

        user_id = user_doc.get('id')
        progress_doc = progress_col.find_one({"user_id": user_id})

        if not progress_doc:
            new_id = _get_next_counter_seq('user_progress')
            base = {
                "id": new_id,
                "user_id": user_id,
                "total_points": 0,
                "streak_days": 0,
                "last_login_date": None,
                "completed_items": json.dumps([]),
                "unlocked_writing_letter": 0,
                "unlocked_writing_lowercase": 0,
                "unlocked_writing_word": 0,
                "unlocked_spelling_letter": 0,
                "unlocked_spelling_word": 0,
                "unlocked_spelling_exam_letter": 0,
                "unlocked_spelling_exam_word": 0,
                "unlocked_writing_exam_letter": 0,
                "unlocked_writing_exam_lowercase": 0,
                "unlocked_writing_exam_word": 0,
                "current_mission_index": 0,
                "completed_missions": json.dumps([]),
            }
            progress_col.insert_one(base)
            progress_doc = base

        return jsonify({
            "status": "success",
            "progress": UserProgress.to_dict(progress_doc)
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengambil progress: {str(e)}"}), 500


@main.route('/api/leaderboard', methods=['GET'])
def get_leaderboard():
    try:
        users_col = db[User.COLLECTION]
        progress_col = db[UserProgress.COLLECTION]

        pipeline = [
            {"$sort": {"total_points": -1}},
            {"$lookup": {
                "from": users_col.name,
                "localField": "user_id",
                "foreignField": "id",
                "as": "user"
            }},
            {"$unwind": "$user"},
            {"$project": {
                "_id": 0,
                "user_id": 1,
                "total_points": 1,
                "name": "$user.nama_lengkap",
                "email": "$user.email",
                "emoji": {"$ifNull": ["$user.profile_pict", "🧒"]}
            }}
        ]

        rows = list(progress_col.aggregate(pipeline))

        results = []
        for rank, row in enumerate(rows, start=1):
            score_formatted = f"{int(row.get('total_points') or 0):,}".replace(',', '.')
            results.append({
                "rank": rank,
                "name": row.get('name'),
                "score": score_formatted,
                "emoji": row.get('emoji') if row.get('emoji') else '🧒',
                "email": row.get('email'),
                "active": False
            })

        return jsonify({"status": "success", "leaderboard": results}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengambil leaderboard: {str(e)}"}), 500


@main.route('/api/activity/log', methods=['POST'])
def add_activity_log():
    data = request.get_json()
    email = data.get('email')
    action = data.get('action')
    description = data.get('description', '')
    points = data.get('points', 0)

    if not email or not action:
        return jsonify({"status": "error", "message": "Email dan action wajib diisi!"}), 400

    try:
        users_col = db[User.COLLECTION]
        logs_col = db[ActivityLog.COLLECTION]

        user_doc = users_col.find_one({"email": email})
        user_doc = _ensure_defaults_user_doc(user_doc)

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        new_log_id = _get_next_counter_seq('activity_logs')

        doc = {
            "id": new_log_id,
            "user_id": user_doc.get("id"),
            "action": action,
            "description": description,
            "points_earned": points,
            "timestamp": _now_ts_str(),
        }

        logs_col.insert_one(doc)

        return jsonify({
            "status": "success",
            "message": "Log aktivitas berhasil disimpan",
            "log": ActivityLog.to_dict(doc)
        }), 201

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal menyimpan log: {str(e)}"}), 500


@main.route('/api/activity/logs', methods=['POST'])
def get_activity_logs():
    data = request.get_json()
    email = data.get('email')

    if not email:
        return jsonify({"status": "error", "message": "Email wajib diisi!"}), 400

    try:
        users_col = db[User.COLLECTION]
        logs_col = db[ActivityLog.COLLECTION]

        user_doc = users_col.find_one({"email": email})
        user_doc = _ensure_defaults_user_doc(user_doc)

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        cursor = logs_col.find({"user_id": user_doc.get('id')}).sort('timestamp', -1).limit(50)
        logs = list(cursor)

        logs_formatted = []
        for doc in logs:
            logs_formatted.append(ActivityLog.to_dict(doc))

        return jsonify({"status": "success", "logs": logs_formatted}), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengambil logs: {str(e)}"}), 500


@main.route('/api/update-profile', methods=['POST'])
def update_profile():
    data = request.get_json()
    email = data.get('email')
    nama_lengkap = data.get('nama_lengkap')
    profile_pict = data.get('profile_pict')

    if not email:
        return jsonify({"status": "error", "message": "Email wajib diisi!"}), 400

    try:
        users_col = db[User.COLLECTION]

        user_doc = users_col.find_one({"email": email})
        user_doc = _ensure_defaults_user_doc(user_doc)

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        update_fields = {}
        if nama_lengkap:
            update_fields['nama_lengkap'] = nama_lengkap
        if profile_pict:
            update_fields['profile_pict'] = profile_pict

        if update_fields:
            update_fields['updated_at'] = _now_ts_str()
            users_col.update_one({"_id": user_doc.get("_id")}, {"$set": update_fields})
            user_doc = users_col.find_one({"_id": user_doc.get("_id")})
            user_doc = _ensure_defaults_user_doc(user_doc)

        return jsonify({
            "status": "success",
            "message": "Profil berhasil diperbarui",
            "user": User.to_dict(user_doc)
        }), 200

    except Exception as e:
        # PyMongo tidak menggunakan db.session.rollback()
        return jsonify({"status": "error", "message": f"Gagal memperbarui profil: {str(e)}"}), 500

@main.route('/api/analytics', methods=['POST'])
def save_analytics():
    if db is None:
        return jsonify({"error": "Koneksi MongoDB bermasalah"}), 500

    try:
        # 1. Tangkap JSON dari Flutter (Gemini Analytics)
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "Tidak ada data JSON yang diterima"}), 400

        # 2. Opsional: Tambahkan waktu server
        data['server_timestamp'] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # 3. Simpan ke MongoDB Atlas
        get_analytics_collection().insert_one(data)
        
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
    if db is None:
        return jsonify({"error": "Koneksi MongoDB bermasalah"}), 500

    email = request.args.get('email')
    if not email:
        return jsonify({"status": "error", "message": "Email diperlukan"}), 400

    try:
        cursor = get_analytics_collection().find({"email": email})
        records = list(cursor)

        if not records:
            return jsonify({
                "status": "success",
                "data": {
                    "skills": [0, 0, 0, 0],
                    "ai_recommendation": "Halo Ayah/Bunda! Ananda belum mulai mengerjakan ujian menulis maupun mengeja. Yuk, ajak Ananda untuk mulai berlatih sekarang! 🚀",
                    "strengths": [],
                    "weaknesses": []
                }
            }), 200

        writing_records = [r for r in records if r.get('mode') == 'writing']
        spelling_records = [r for r in records if r.get('mode') == 'spelling']
        observasi_records = [r for r in records if r.get('mode') == 'observasi']
        duel_records = [r for r in records if r.get('mode') == 'duel']
        
        # Akurasi Menulis
        writing_accuracy = sum(r.get('accuracy_score', 0) for r in writing_records) / len(writing_records) if writing_records else 0
        
        # Akurasi Mengeja
        spelling_accuracy = sum(r.get('accuracy_score', 0) for r in spelling_records) / len(spelling_records) if spelling_records else 0

        # Akurasi Observasi
        observasi_accuracy = sum(r.get('accuracy_score', 0) for r in observasi_records) / len(observasi_records) if observasi_records else 0

        # Akurasi Duel
        duel_accuracy = sum(r.get('accuracy_score', 0) for r in duel_records) / len(duel_records) if duel_records else 0

        def get_wrong_letters(record_list):
            counts = {}
            for r in record_list:
                for w in r.get('wrong_letters', []):
                    if w:
                        w_str = f"kapital '{w}'" if w.isupper() else f"kecil '{w}'"
                        counts[w_str] = counts.get(w_str, 0) + 1
            return counts

        def get_error_types(record_list):
            counts = {}
            for r in record_list:
                err = r.get('error_type')
                if err and err != "benar":
                    counts[err] = counts.get(err, 0) + 1
            return counts

        writing_wrong_letters = get_wrong_letters(writing_records)
        spelling_wrong_letters = get_wrong_letters(spelling_records)

        writing_errors = get_error_types(writing_records)
        spelling_errors = get_error_types(spelling_records)

        strengths = []
        weaknesses = []

        # Analisis Menulis
        if writing_records:
            if writing_accuracy >= 80:
                strengths.append(f"Akurasi menulis sangat baik mencapai {writing_accuracy:.0f}%.")
            elif writing_accuracy >= 60:
                strengths.append(f"Akurasi menulis cukup baik ({writing_accuracy:.0f}%), namun masih bisa dimaksimalkan.")
            else:
                weaknesses.append(f"Akurasi menulis perlu ditingkatkan (saat ini {writing_accuracy:.0f}%).")
            
            if writing_wrong_letters:
                most_wrong_writing = max(writing_wrong_letters, key=writing_wrong_letters.get)
                weaknesses.append(f"Sering terbalik/kesulitan saat menulis huruf {most_wrong_writing}.")
            
            if writing_errors:
                most_common_w_err = max(writing_errors, key=writing_errors.get).replace('_', ' ')
                weaknesses.append(f"Tipe kesalahan penulisan dominan: {most_common_w_err}.")
            elif writing_accuracy > 90:
                strengths.append("Hampir tidak ada kesalahan bentuk dalam penulisan.")

        # Analisis Mengeja
        if spelling_records:
            if spelling_accuracy >= 80:
                strengths.append(f"Akurasi mengeja sangat baik mencapai {spelling_accuracy:.0f}%.")
            elif spelling_accuracy >= 60:
                strengths.append(f"Akurasi mengeja cukup baik ({spelling_accuracy:.0f}%), terus tingkatkan.")
            else:
                weaknesses.append(f"Akurasi mengeja perlu ditingkatkan (saat ini {spelling_accuracy:.0f}%).")
            
            if spelling_wrong_letters:
                most_wrong_spelling = max(spelling_wrong_letters, key=spelling_wrong_letters.get)
                weaknesses.append(f"Sering kesulitan saat mengeja huruf/suku kata {most_wrong_spelling}.")
            
            if spelling_errors:
                most_common_s_err = max(spelling_errors, key=spelling_errors.get).replace('_', ' ')
                weaknesses.append(f"Tipe kesalahan ejaan dominan: {most_common_s_err}.")

        # Analisis Observasi
        if observasi_records:
            if observasi_accuracy >= 80:
                strengths.append(f"Fokus dan kemampuan observasi benda sangat baik ({observasi_accuracy:.0f}%).")
            else:
                weaknesses.append(f"Fokus observasi perlu dilatih lagi (saat ini {observasi_accuracy:.0f}%).")

        # Analisis Duel
        if duel_records:
            if duel_accuracy >= 50:
                strengths.append(f"Tangkas dalam kompetisi duel multiplayer ({duel_accuracy:.0f}% kemenangan/seri).")
            else:
                weaknesses.append(f"Kecepatan menyusun kata di mode duel perlu ditingkatkan.")

        # Pesan AI Executive Summary
        ai_recommendation = "Halo Ayah/Bunda! Perkembangan belajar Ananda sungguh luar biasa! "
        if writing_wrong_letters and spelling_wrong_letters:
            most_wrong_writing = max(writing_wrong_letters, key=writing_wrong_letters.get)
            most_wrong_spelling = max(spelling_wrong_letters, key=spelling_wrong_letters.get)
            ai_recommendation = f"Halo Ayah/Bunda! Ananda menunjukkan semangat yang tinggi. Saat ini, Ananda butuh bimbingan ekstra untuk melatih penulisan {most_wrong_writing} dan ejaan {most_wrong_spelling}. Yuk, temani Ananda berlatih di rumah!"
        elif writing_wrong_letters:
            most_wrong_writing = max(writing_wrong_letters, key=writing_wrong_letters.get)
            ai_recommendation = f"Halo Ayah/Bunda! Ananda sangat hebat dalam mengeja, tapi butuh sedikit bimbingan ekstra untuk melatih bentuk tulisan {most_wrong_writing}. Yuk berlatih menulis lebih sering!"
        elif spelling_wrong_letters:
            most_wrong_spelling = max(spelling_wrong_letters, key=spelling_wrong_letters.get)
            ai_recommendation = f"Halo Ayah/Bunda! Tulisan Ananda sudah rapi, tapi masih sering kesulitan saat mengeja {most_wrong_spelling}. Yuk, ajak Ananda berlatih melafalkan ejaan bersama!"
        elif writing_accuracy >= 80 and spelling_accuracy >= 80:
            ai_recommendation = "Halo Ayah/Bunda! Perkembangan belajar Ananda sungguh luar biasa! Keterampilan menulis dan mengejanya sudah sangat rapi dan akurat. Terus berikan pujian untuk menjaga semangatnya ya!"
        else:
            ai_recommendation = "Halo Ayah/Bunda! Ananda sedang dalam tahap beradaptasi dengan bentuk huruf dan pelafalannya. Dampingi Ananda dan gunakan fitur 'Latihan' agar semakin lancar."

        # Ekstrak data trend akurasi gabungan (maksimal 10 ujian terakhir)
        accuracy_trend = [r.get('accuracy_score', 0) for r in records[-10:]]

        return jsonify({
            "status": "success",
            "data": {
                # Urutan: Menulis, Mengeja, Observasi, Duel
                "skills": [writing_accuracy, spelling_accuracy, observasi_accuracy, duel_accuracy],
                "ai_recommendation": ai_recommendation,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "accuracy_trend": accuracy_trend
            }
        }), 200

    except Exception as e:
        print(f"Error saat mengambil raport: {e}")
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
#  SESSION TRACKING — Endpoints baru untuk melacak durasi penggunaan aplikasi
#  Digunakan oleh Admin Dashboard. Tidak mempengaruhi fitur Flutter yang lain.
# ─────────────────────────────────────────────────────────────────────────────

@main.route('/api/session/start', methods=['POST'])
def session_start():
    """
    Mencatat awal sesi penggunaan aplikasi.
    Dipanggil Flutter saat aplikasi dibuka / user login.

    Body JSON:
        email (str): Email pengguna
        device_info (str, optional): Info perangkat
    """
    data = request.get_json() or {}
    email = data.get('email', '').strip()

    if not email:
        return jsonify({"status": "error", "message": "Email wajib diisi!"}), 400

    try:
        from app.models import AppSession
        users_col = db[User.COLLECTION]
        sessions_col = db[AppSession.COLLECTION]

        user_doc = users_col.find_one({"email": email})
        user_doc = _ensure_defaults_user_doc(user_doc)

        if not user_doc:
            return jsonify({"status": "error", "message": "User tidak ditemukan!"}), 404

        session_id = _get_next_counter_seq('app_sessions')
        now_str = _now_ts_str()

        session_doc = {
            "id": session_id,
            "user_id": user_doc.get("id"),
            "session_start": now_str,
            "session_end": None,
            "duration_seconds": None,
            "device_info": data.get("device_info", ""),
        }

        sessions_col.insert_one(session_doc)

        return jsonify({
            "status": "success",
            "message": "Sesi dimulai",
            "session_id": session_id,
        }), 201

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal memulai sesi: {str(e)}"}), 500


@main.route('/api/session/end', methods=['POST'])
def session_end():
    """
    Mencatat akhir sesi dan menghitung durasi penggunaan.
    Dipanggil Flutter saat aplikasi ditutup / user logout.

    Body JSON:
        session_id (int): ID sesi dari /api/session/start
        email (str): Email pengguna (sebagai validasi)
    """
    data = request.get_json() or {}
    session_id = data.get('session_id')
    email = data.get('email', '').strip()

    if not session_id:
        return jsonify({"status": "error", "message": "session_id wajib diisi!"}), 400

    try:
        from app.models import AppSession

        sessions_col = db[AppSession.COLLECTION]
        session_doc = sessions_col.find_one({"id": session_id})

        if not session_doc:
            return jsonify({"status": "error", "message": "Sesi tidak ditemukan!"}), 404

        if session_doc.get("session_end") is not None:
            return jsonify({"status": "error", "message": "Sesi sudah diakhiri sebelumnya!"}), 400

        now_str = _now_ts_str()

        # Hitung durasi
        start_str = session_doc.get("session_start", "")
        duration_seconds = None
        try:
            start_dt = datetime.datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.datetime.strptime(now_str, "%Y-%m-%d %H:%M:%S")
            duration_seconds = int((end_dt - start_dt).total_seconds())
        except Exception:
            pass

        sessions_col.update_one(
            {"id": session_id},
            {"$set": {
                "session_end": now_str,
                "duration_seconds": duration_seconds,
            }}
        )

        return jsonify({
            "status": "success",
            "message": "Sesi diakhiri",
            "duration_seconds": duration_seconds,
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": f"Gagal mengakhiri sesi: {str(e)}"}), 500
