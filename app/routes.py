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
from app.extensions import db  # MongoDB handle
from app.models import User, UserProgress, ActivityLog

from app.ai.predictor import predict_image
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pymongo import MongoClient


main = Blueprint('main', __name__)


# --- KONFIGURASI EMAIL PENGIRIM ---
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

# --- MONGODB ATLAS CONNECTION ---
MONGO_URI = os.getenv("MONGO_URI")
mongo_client = MongoClient(MONGO_URI) if MONGO_URI else None
mongo_db = mongo_client['edutech_db'] if mongo_client is not None else None
mongo_collection = mongo_db['writing_analytics'] if mongo_db is not None else None


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

    if not user_doc or not check_password_hash(user_doc.get("password"), password):
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


@main.route('/api/ujian-menulis-gemini', methods=['POST'])
def ujian_menulis_gemini():
    import time
    import logging
    import concurrent.futures

    print("===== REQUEST =====")
    print("FORM :", request.form)
    print("FILES:", request.files)
    print("===================")

    start_time = time.time()
    app_logger = logging.getLogger(__name__)

    model_param = (request.form.get('model', 'cnn') or 'cnn').strip().lower()
    target = (request.form.get('target', 'A') or 'A').upper().strip()
    kategori = (request.form.get('kategori', 'huruf') or 'huruf').lower().strip()
    hasil_ocr = (request.form.get('hasil_ocr', '') or '').strip()
    transkripsi = (request.form.get('transkripsi', '') or '').strip()
    mode = (request.form.get('mode', 'writing') or 'writing').strip().lower()

    transkripsi = (transkripsi or '').lower().strip()
    target = (target or '').lower().strip()
    transkripsi = " ".join(transkripsi.split())
    target = " ".join(target.split())

    print(f"mode={mode}")
    print(f"target={target}")
    print(f"kategori={kategori}")
    print(f"transkripsi={transkripsi}")
    print(f"hasil_ocr={hasil_ocr}")

    if mode not in ('writing', 'reading', 'spelling'):
        return jsonify({"status": "error", "message": "Field mode harus diisi dengan 'writing', 'spelling', atau 'reading'."}), 400

    if model_param not in ('cnn', 'mlkit'):
        return jsonify({"status": "error", "message": "Parameter model tidak valid. Gunakan 'cnn' atau 'mlkit'."}), 400

    if not target:
        return jsonify({"status": "error", "message": "Field target wajib diisi."}), 400

    if not kategori:
        return jsonify({"status": "error", "message": "Field kategori wajib diisi."}), 400

    hasil_cnn = None

    app_logger.info(
        "[ujian-menulis-gemini] start model=%s mode=%s target=%s kategori=%s",
        model_param, mode, target, kategori
    )

    def _extract_status_code(e, default=None):
        for attr in ("status_code", "code", "status", "http_status"):
            if hasattr(e, attr):
                try:
                    val = getattr(e, attr)
                    if isinstance(val, int):
                        return val
                except Exception:
                    pass

        s = str(e) if e is not None else ""
        m = re.search(r"\b(3\d\d)\b", s)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return default

    def _handle_gemini_error(e):
        raw_msg = str(e)
        exc_type = type(e).__name__
        status_code = _extract_status_code(e)

        app_logger.error(
            "[ujian-menulis-gemini] gemini exception type=%s status_code=%s raw_message=%s",
            exc_type, status_code, raw_msg
        )

        s = raw_msg.upper()

        is_server_error = ("SERVERERROR" in s) or ("GOOGLE.GENAI.ERRORS.SERVERERROR" in s)
        is_503_unavailable_high_demand = (
            (status_code == 503 or "503" in s) and
            ("UNAVAILABLE" in s) and
            ("HIGH DEMAND" in s)
        )
        if is_server_error or is_503_unavailable_high_demand:
            return 503, {"status": "error", "message": "AI sedang sibuk karena banyak permintaan. Silakan coba lagi beberapa saat."}

        is_resource_exhausted = ("RESOURCE_EXHAUSTED" in s)
        is_quota_exceeded = ("QUOTA EXCEEDED" in s) or ("QUOTA" in s and "EXCEEDED" in s)
        is_429 = (status_code == 429) or ("429" in s)
        if is_resource_exhausted or is_quota_exceeded or is_429:
            return 429, {"status": "error", "message": "Kuota API Gemini telah habis. Silakan coba lagi nanti."}

        return 500, {"status": "error", "message": raw_msg}

    try:
        if mode == 'writing':
            if model_param == 'cnn':
                if 'gambar' in request.files:
                    file_gambar = request.files['gambar']
                    ocr_result = predict_image(file_gambar)
                    hasil_ocr = (ocr_result.get('prediction') or '').strip()
                    hasil_cnn = {"prediction": ocr_result.get('prediction'), "confidence": ocr_result.get('confidence')}
                elif hasil_ocr:
                    hasil_cnn = None
                else:
                    return jsonify({"status": "error", "message": "Field image/gambar atau hasil_ocr wajib diisi untuk mode writing."}), 400
            else:
                if not hasil_ocr:
                    return jsonify({"status": "error", "message": "Field hasil_ocr wajib diisi untuk mode writing dengan model='mlkit'."}), 400

            if not hasil_ocr:
                return jsonify({"status": "error", "message": "Hasil OCR tidak ditemukan."}), 400

        elif mode in ('spelling', 'reading'):
            if not transkripsi:
                return jsonify({"status": "error", "message": f"Field transkripsi wajib diisi untuk mode {mode}."}), 400
            hasil_ocr = transkripsi

        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            return jsonify({"status": "error", "message": "GEMINI_API_KEY tidak ditemukan di environment runtime"}), 500

        local_client = genai.Client(api_key=gemini_key)

        if mode == 'writing':
            prompt = f"""Kamu adalah guru SD yang ramah, sabar, dan penyemangat.
Tugasmu BUKAN membaca gambar atau melakukan OCR.
Tugasmu adalah MENGEVALUASI hasil tulisan anak berdasarkan teks yang sudah dikirimkan kepadamu.

Informasi yang kamu terima:
- Hasil OCR (teks tulisan anak): "{hasil_ocr}"
- Jawaban yang benar: "{target}"
- Jenis ujian: "{kategori}" (nilai: 'huruf' atau 'kata')

Langkah 1 — Tentukan status:
- Bandingkan hasil tulisan dengan jawaban benar (abaikan huruf besar/kecil).
- Jika sama → status = "benar"
- Jika berbeda → status = "salah"

Langkah 2 — Buat feedback:
- Jika status = "salah": jelaskan letak kesalahannya secara sederhana, sebutkan huruf/kata yang salah dan yang seharusnya, lalu beri semangat untuk mencoba lagi.
  Jika jenis ujian = 'kata' dan ada huruf yang kurang baik, sebutkan huruf tersebut.
- Jika status = "benar": beri pujian yang hangat.
  Jika tulisan masih kurang rapi, berikan saran yang lembut agar makin baik.

Jawab HANYA dalam format JSON berikut:
{{
  "status": "benar" atau "salah",
  "feedback": "kalimat evaluasi singkat",
  "tts": "kalimat yang akan dibacakan"
}}"""

        elif mode == 'reading':
            prompt = f"""Kamu adalah guru SD yang ramah, sabar, dan penyemangat.
Tugasmu adalah MENGEVALUASI kemampuan membaca anak berdasarkan teks yang sudah dikirimkan kepadamu.

Informasi yang kamu terima:
- Teks hasil baca anak: "{hasil_ocr}"
- Jawaban yang benar: "{target}"
- Jenis ujian: "{kategori}" (nilai: 'huruf' atau 'kata')

Langkah 1 — Tentukan status:
- Bandingkan teks hasil baca dengan jawaban benar (abaikan huruf besar/kecil).
- Jika sama → status = "benar"
- Jika berbeda → status = "salah"

Jawab HANYA dalam format JSON berikut:
{{
  "status": "benar" atau "salah",
  "feedback": "kalimat evaluasi singkat",
  "tts": "kalimat yang akan dibacakan"
}}"""

        else:
            prompt = f"""Kamu adalah guru terapi wicara dan guru membaca anak usia 4–8 tahun.
Tugasmu menilai pelafalan suara anak berdasarkan transkripsi hasil STT.

Target: "{target}"
Transkripsi: "{hasil_ocr}"

Jawab HANYA dalam format JSON berikut:
{{
  "status": "benar" atau "salah",
  "feedback": "kalimat evaluasi singkat",
  "tts": "kalimat yang akan dibacakan"
}}"""

        def call_gemini():
            return local_client.models.generate_content(model='gemini-2.5-flash', contents=[prompt])

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(call_gemini)
            response = future.result(timeout=25)

        clean_text = (response.text or '').strip()
        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].strip()

        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            clean_text = clean_text[start_idx:end_idx]

        hasil_json = json.loads(clean_text)
        status_eval = hasil_json.get('status', 'salah')
        feedback = hasil_json.get('feedback', '')
        tts = hasil_json.get('tts', '')
        result = "correct" if status_eval == "benar" else "incorrect"

        return jsonify({"status": "success", "result": result, "feedback": feedback, "tts": tts}), 200

    except concurrent.futures.TimeoutError:
        return jsonify({"status": "error", "message": "Proses evaluasi memakan waktu terlalu lama. Coba lagi ya."}), 504

    except json.JSONDecodeError:
        return jsonify({"status": "error", "message": "Gemini gagal mengembalikan format data yang sesuai."}), 500

    except Exception as e:
        http_status, response_json = _handle_gemini_error(e)
        return jsonify(response_json), http_status


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
                "current_mission_index": 0,
                "completed_missions": json.dumps([]),
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

        if 'current_mission_index' in data:
            update_fields['current_mission_index'] = data['current_mission_index']
        if 'completed_missions' in data:
            update_fields['completed_missions'] = json.dumps(data['completed_missions'])

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
        return jsonify({"status": "error", "message": f"Gagal memperbarui profil: {str(e)}"}), 500


@main.route('/api/predict', methods=['POST'])
def predict_handwriting():
    if 'gambar' not in request.files:
        return jsonify({"status": "error", "message": "File gambar tidak ditemukan"}), 400

    try:
        file = request.files['gambar']
        result = predict_image(file)

        return jsonify({
            "status": "success",
            "prediction": result["prediction"],
            "confidence": result["confidence"]
        }), 200

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


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
