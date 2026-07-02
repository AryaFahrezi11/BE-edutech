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
from app.ai.predictor import predict_image
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

main = Blueprint('main', __name__)



# --- KONFIGURASI EMAIL PENGIRIM ---
SENDER_EMAIL = os.getenv("SENDER_EMAIL") 
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")

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
    import time
    import logging
    import concurrent.futures 

    start_time = time.time()
    app_logger = logging.getLogger(__name__)

    model_param = (request.form.get('model', 'cnn') or 'cnn').strip().lower()  # 'cnn' | 'mlkit'
    target = (request.form.get('target', 'A') or 'A').upper().strip()
    kategori = (request.form.get('kategori', 'huruf') or 'huruf').lower().strip()  # 'huruf' | 'kata'
    hasil_ocr = (request.form.get('hasil_ocr', '') or '').strip()

    # untuk logging (tidak dikirim ke client)
    hasil_cnn = None

    app_logger.info(
        "[ujian-menulis-gemini] start model=%s target=%s kategori=%s",
        model_param, target, kategori
    )

    if model_param not in ('cnn', 'mlkit'):
        return jsonify({"status": "error", "message": "Parameter model tidak valid. Gunakan 'cnn' atau 'mlkit'."}), 400

    def _extract_status_code(e, default=None):
        # coba ambil dari atribut umum
        for attr in ("status_code", "code", "status", "http_status"):
            if hasattr(e, attr):
                try:
                    val = getattr(e, attr)
                    if isinstance(val, int):
                        return val
                except Exception:
                    pass

        # fallback dari string
        s = str(e) if e is not None else ""
        m = re.search(r"\b(3\d\d)\b", s)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                pass
        return default

    def _handle_gemini_error(e):
        """Return (http_status, response_json_dict) untuk exception Gemini."""
        raw_msg = str(e)
        exc_type = type(e).__name__
        status_code = _extract_status_code(e)

        # Logging sesuai permintaan
        app_logger.error(
            "[ujian-menulis-gemini] gemini exception type=%s status_code=%s raw_message=%s",
            exc_type, status_code, raw_msg
        )

        s = raw_msg.upper()

        # 1) high demand: ServerError 503 UNAVAILABLE ... high demand
        is_server_error = ("SERVERERROR" in s) or ("GOOGLE.GENAI.ERRORS.SERVERERROR" in s)
        is_503_unavailable_high_demand = (
            (status_code == 503 or "503" in s) and
            ("UNAVAILABLE" in s) and
            ("HIGH DEMAND" in s)
        )
        if is_server_error or is_503_unavailable_high_demand:
            return 503, {
                "status": "error",
                "message": "AI sedang sibuk karena banyak permintaan. Silakan coba lagi beberapa saat."
            }

        # 2) quota exceeded: RESOURCE_EXHAUSTED / Quota exceeded / HTTP 429
        is_resource_exhausted = ("RESOURCE_EXHAUSTED" in s)
        is_quota_exceeded = ("QUOTA EXCEEDED" in s) or ("QUOTA" in s and "EXCEEDED" in s)
        is_429 = (status_code == 429) or ("429" in s)
        if is_resource_exhausted or is_quota_exceeded or is_429:
            return 429, {
                "status": "error",
                "message": "Kuota API Gemini telah habis. Silakan coba lagi nanti."
            }

        # 3) lainnya => 500, message = pesan error sebenarnya
        return 500, {"status": "error", "message": raw_msg}

    try:
        # OCR stage (hanya untuk cnn)
        if model_param == 'cnn':
            if 'gambar' not in request.files:
                return jsonify({"status": "error", "message": "File gambar tidak ditemukan!"}), 400

            file_gambar = request.files['gambar']
            ocr_result = predict_image(file_gambar)  # {prediction, confidence}
            hasil_ocr = (ocr_result.get('prediction') or '').strip()
            hasil_cnn = {
                "prediction": ocr_result.get('prediction'),
                "confidence": ocr_result.get('confidence')
            }
        else:
            if not hasil_ocr:
                return jsonify({"status": "error", "message": "Hasil OCR tidak ditemukan untuk model='mlkit'!"}), 400

        if not hasil_ocr:
            return jsonify({"status": "error", "message": "Hasil OCR tidak ditemukan!"}), 400

        # Gemini evaluator stage
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            return jsonify({"status": "error", "message": "GEMINI_API_KEY tidak ditemukan di environment runtime"}), 500

        local_client = genai.Client(api_key=gemini_key)

        # Satu prompt yang sama untuk kedua model
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

=== ATURAN PENULISAN ===
- Bahasa Indonesia yang singkat, positif, ramah anak SD.
- Maksimal 2 kalimat untuk field "feedback".
- Jangan gunakan istilah teknis (jangan sebut OCR, gambar, model AI, dll).
- Field "tts" untuk Text-to-Speech, tanpa simbol aneh.

Jawab HANYA dalam format JSON berikut:
{{
  "status": "benar" atau "salah",
  "feedback": "kalimat evaluasi singkat",
  "tts": "kalimat yang akan dibacakan"
}}"""

        def call_gemini():
            return local_client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt]
            )

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

        total_time_ms = int((time.time() - start_time) * 1000)
        response_json = {
            "status": "success",
            "result": result,
            "feedback": feedback,
            "tts": tts
        }

        app_logger.info(
            "[ujian-menulis-gemini] done model=%s target=%s hasil_ocr=%s hasil_cnn=%s feedback=%s waktu_ms=%s response_json=%s",
            model_param, target, hasil_ocr, hasil_cnn, feedback, total_time_ms, response_json
        )

        return jsonify(response_json), 200

    except concurrent.futures.TimeoutError:

        total_time_ms = int((time.time() - start_time) * 1000)
        response_json = {
            "status": "error",
            "message": "Proses evaluasi memakan waktu terlalu lama. Coba lagi ya."
        }
        app_logger.error(
            "[ujian-menulis-gemini] timeout model=%s target=%s hasil_ocr=%s hasil_cnn=%s feedback=%s waktu_ms=%s response_json=%s",
            model_param, target, hasil_ocr, hasil_cnn, None, total_time_ms, response_json
        )
        return jsonify(response_json), 504

    except json.JSONDecodeError:
        total_time_ms = int((time.time() - start_time) * 1000)
        response_json = {
            "status": "error",
            "message": "Gemini gagal mengembalikan format data yang sesuai."
        }
        app_logger.exception(
            "[ujian-menulis-gemini] JSONDecodeError model=%s target=%s hasil_ocr=%s hasil_cnn=%s feedback=%s waktu_ms=%s response_json=%s",
            model_param, target, hasil_ocr, hasil_cnn, None, total_time_ms, response_json
        )
        return jsonify(response_json), 500

    except Exception as e:
        http_status, response_json = _handle_gemini_error(e)
        return jsonify(response_json), http_status



    



    # Endpoint tidak diubah sesuai instruksi.
    if request.content_type and 'multipart/form-data' not in request.content_type:
        # tetap izinkan, tapi untuk project ini biasanya flutter kirim multipart
        pass


    target = request.form.get('target_huruf_atau_kata', '').strip()
    hasil_ocr = request.form.get('hasil_ocr', '').strip()
    model_lokasi = request.form.get('model', '').strip()

    if not target:
        return jsonify({"status": "error", "message": "target_huruf_atau_kata wajib diisi!"}), 400
    if not hasil_ocr:
        return jsonify({"status": "error", "message": "hasil_ocr wajib diisi!"}), 400

    try:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            return jsonify({"status": "error", "message": "GEMINI_API_KEY tidak ditemukan di environment runtime"}), 500

        local_client = genai.Client(api_key=gemini_key)

        # Tentukan kategori: huruf (1 karakter) atau kata
        stripped_target = target.replace(' ', '')
        jenis_ujian = 'huruf' if len(stripped_target) == 1 else 'kata'
        jawaban_benar = stripped_target.upper()  # normalisasi untuk pembandingan

        prompt = f"""Kamu adalah guru SD yang ramah, sabar, dan penyemangat.
Tugasmu BUKAN membaca gambar atau melakukan OCR.
Tugasmu adalah MENGEVALUASI hasil tulisan anak berdasarkan teks yang sudah dikirimkan kepadamu.

Informasi yang kamu terima:
- Target (huruf atau kata yang seharusnya ditulis): "{jawaban_benar}"
- Hasil OCR (teks tulisan anak yang sudah terbaca oleh sistem): "{hasil_ocr}"
- Jenis ujian: "{jenis_ujian}" (nilai: 'huruf' untuk satu huruf, 'kata' untuk satu kata)
- Keterangan model (hanya info tambahan, tidak perlu dibahas ke anak): "{model_lokasi}"

=== LANGKAH EVALUASI ===
Langkah 1 — Tentukan status:
- Bandingkan hasil OCR dengan target (abaikan perbedaan huruf besar-kecil).
- Jika sama → status = "benar"
- Jika berbeda → status = "salah"

Langkah 2 — Buat feedback berdasarkan status:

>> Jika status = "salah":
1) Jelaskan kemungkinan kesalahannya.
2) Sebutkan kesalahan yang cocok dengan contoh ini:
   - Garis masih kurang lurus.
   - Lengkungan masih kurang rapi.
   - Huruf masih terlihat seperti huruf lain.
   - Coba tulis lebih pelan.
3) Jika jenis ujian = 'huruf': sebutkan bentuk huruf yang perlu diperbaiki dengan contoh:
   - garisnya bisa dibuat lebih lurus
   - lengkungannya bisa dibuat lebih rapi
   - ukurannya bisa dibuat lebih besar
   - hurufnya bisa dibuat lebih jelas
4) Jika jenis ujian = 'kata': sebutkan huruf tertentu yang kurang rapi bila memungkinkan.
   Contoh pola kalimat: "Huruf B pada kata \"BOLA\" masih kurang rapi, coba buat lengkungannya lebih jelas ya."
5) Tutup dengan kalimat semangat agar anak mau mencoba lagi.

>> Jika status = "benar":
1) Berikan pujian yang hangat dan menyemangatkan.
2) Jika bentuk masih kurang rapi, beri saran lembut (maks 1 saran).
   Contoh:
   - Huruf A sudah benar, tetapi garis kirinya bisa dibuat lebih lurus.
   - Huruf B sudah bagus, lengkungan atas bisa dibuat sedikit lebih bulat.
   - Tulisanmu sudah benar, coba ukuran huruf dibuat lebih konsisten.

=== ATURAN PENULISAN ===
- Gunakan bahasa Indonesia yang singkat, positif, dan ramah anak SD.
- Field "feedback" maksimal 2 kalimat.
- Jangan gunakan istilah teknis (jangan sebut OCR, gambar, model AI, dll).
- Field "tts" berisi kalimat yang akan dibacakan oleh Text To Speech.
  Pastikan "tts":
  - tidak mengandung simbol seperti *, #, /, \\ atau tanda baca aneh
  - terdengar natural saat dibacakan
  - boleh sedikit berbeda dari feedback supaya enak didengar.

Jawab HANYA dalam format JSON berikut (tanpa markdown, tanpa komentar, tanpa teks lain di luar JSON):
{{
  "status": "benar" atau "salah",
  "feedback": "kalimat evaluasi singkat untuk ditampilkan di layar aplikasi",
  "tts": "kalimat yang akan langsung dibacakan ke anak melalui Text to Speech"
}}"""

        response = local_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt]
        )

        clean_text = response.text.strip()

        if "```json" in clean_text:
            clean_text = clean_text.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_text:
            clean_text = clean_text.split("```")[1].strip()

        start_idx = clean_text.find("{")
        end_idx = clean_text.rfind("}") + 1
        if start_idx != -1 and end_idx > start_idx:
            clean_text = clean_text[start_idx:end_idx]

        hasil_json = json.loads(clean_text)

        return jsonify({
            "status": hasil_json.get("status", "salah"),
            "feedback": hasil_json.get("feedback", ""),
            "tts": hasil_json.get("tts", "")
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

@main.route('/api/predict', methods=['POST'])
def predict_handwriting():

    if 'gambar' not in request.files:
        return jsonify({
            "status": "error",
            "message": "File gambar tidak ditemukan"
        }), 400

    try:
        file = request.files['gambar']

        result = predict_image(file)

        return jsonify({
            "status": "success",
            "prediction": result["prediction"],
            "confidence": result["confidence"]
        }), 200

    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

