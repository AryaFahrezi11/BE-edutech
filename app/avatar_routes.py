import os
import time
import requests
from flask import Blueprint, request, jsonify
from google import genai

avatar_bp = Blueprint('avatar', __name__)

# --- HELPER D-ID API KEY ROTATION ---
current_key_index = 0

def get_d_id_api_keys():
    """Mengambil daftar API Keys dari .env"""
    keys_raw = os.getenv("DID_API_KEYS", "")
    return [k.strip() for k in keys_raw.split(",") if k.strip()]

def get_avatar_image_url():
    """Mengambil Public URL Avatar Gambar dari .env"""
    return os.getenv(
        "AVATAR_IMAGE_URL",
        "https://files.catbox.moe/cvyv9s.jpg"
    )

def make_did_request(method, url, json_payload=None):
    """
    Melakukan HTTP request ke D-ID API dengan fitur Rotasi Key Otomatis
    apabila terjadi Limit/402 Payment Required.
    """
    global current_key_index
    keys = get_d_id_api_keys()

    if not keys:
        raise Exception("DID_API_KEYS belum dikonfigurasi di file .env!")

    attempts = 0
    max_attempts = len(keys)

    while attempts < max_attempts:
        idx = current_key_index % len(keys)
        active_key = keys[idx]

        import base64
        auth_header = active_key if active_key.startswith("Basic ") else f"Basic {base64.b64encode(active_key.encode()).decode()}" if ":" in active_key else f"Basic {active_key}"
        headers = {
            "Authorization": auth_header,
            "Content-Type": "application/json"
        }

        try:
            if method.upper() == "POST":
                resp = requests.post(url, json=json_payload, headers=headers, timeout=60)
            elif method.upper() == "GET":
                resp = requests.get(url, headers=headers, timeout=60)
            elif method.upper() == "DELETE":
                resp = requests.delete(url, json=json_payload, headers=headers, timeout=60)
            else:
                raise ValueError(f"Method {method} tidak didukung.")

            # 402 Payment Required / Insufficient credits
            if resp.status_code == 402 or "Insufficient credits" in resp.text or "PaymentRequired" in resp.text:
                print(f"[D-ID API Rotasi] [WARNING] Key index {idx} habis/limit. Beralih ke key berikutnya...")

                current_key_index = (current_key_index + 1) % len(keys)
                attempts += 1
                continue

            try:
                data = resp.json()
            except Exception:
                data = {"raw_text": resp.text}

            return data, resp.status_code, idx

        except requests.RequestException as e:
            print(f"[D-ID API Error] Request gagal pada key index {idx}: {e}")
            current_key_index = (current_key_index + 1) % len(keys)
            attempts += 1

    raise Exception("Semua D-ID API Keys yang terdaftar telah kehabisan kredit!")


# --- ENDPOINT 1: MP4 TALK GENERATION (GEMINI + D-ID TALKS) ---
@avatar_bp.route('/api/avatar/chat', methods=['POST'])
def avatar_chat():
    """
    Endpoint utama percakapan Avatar:
    1. Menerima 'prompt' dari user.
    2. Mengirim prompt ke Gemini AI untuk mendapatkan teks balasan.
    3. Mengirim teks balasan ke D-ID API (/talks) untuk generate video animasi MP4.
    4. Melakukan polling hingga video selesai (.mp4), lalu mengembalikan video_url ke client.
    """
    try:
        req_data = request.get_json() or {}
        user_prompt = req_data.get('prompt', '').strip()
        voice_id = req_data.get('voice_id', 'id-ID-GadisNeural')  # Default suara Bu Guru (Wanita Indonesia Ramah)

        if not user_prompt:
            return jsonify({"status": "error", "message": "Prompt tidak boleh kosong!"}), 400

        # Step 1: Generate teks balasan dari Gemini AI
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            return jsonify({"status": "error", "message": "GEMINI_API_KEY belum dikonfigurasi di .env!"}), 500

        print(f"[AI Avatar] Memproses prompt user: '{user_prompt}' dengan Gemini...")
        client = genai.Client(api_key=gemini_api_key)
        
        # System Prompt Persona: Bu Guru SD/TK/PAUD yang Penyayang, Ramah, dan Murah Senyum
        system_instruction = (
            "Kamu adalah 'Bu Guru Ani', seorang guru TK, PAUD, dan SD kelas 1-2 yang sangat penyayang, sabar, ramah, dan murah senyum. "
            "Audiensmu adalah anak-anak kecil yang belum bisa membaca atau sedang belajar membaca. "
            "Aturan gaya bicaramu:\n"
            "1. Gunakan bahasa Indonesia yang sangat sederhana, lembut, ceria, dan mudah dipahami anak kecil.\n"
            "2. Gunakan kata sapaan yang hangat dan penyayang seperti 'Sayang', 'Adik pintar', 'Anak hebat'.\n"
            "3. Seringlah memberikan pujian dan semangat (seperti 'Wah hebat sekali!', 'Pintar banget!').\n"
            "4. Panjang jawaban maksimal 2-3 kalimat pendek saja agar anak-anak tidak bosan mendengarkannya.\n"
            "5. Jika menjelaskan sesuatu, gunakan contoh sederhana yang disukai anak-anak (seperti hewan, warna, mainan, atau buah)."
        )


        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=f"{system_instruction}\n\nPertanyaan User: {user_prompt}"
        )

        ai_text_response = response.text.strip() if response and response.text else "Maaf, saya tidak dapat memahami pertanyaan tersebut."
        print(f"[AI Avatar] Jawaban Gemini: '{ai_text_response}'")

        # Step 2: Mengirim teks ke D-ID API /talks
        did_payload = {
            "script": {
                "type": "text",
                "subtitles": False,
                "provider": {
                    "type": "microsoft",
                    "voice_id": voice_id
                },
                "input": ai_text_response
            },
            "config": {
                "fluent": False,
                "pad_audio": 0.0
            },
            "source_url": get_avatar_image_url()
        }

        print("[AI Avatar] Membuat video animasi D-ID...")
        create_res, status_code, key_idx = make_did_request("POST", "https://api.d-id.com/talks", did_payload)

        if status_code not in [200, 201] or "id" not in create_res:
            return jsonify({
                "status": "error",
                "message": "Gagal membuat job video D-ID",
                "details": create_res
            }), status_code

        talk_id = create_res["id"]
        print(f"[AI Avatar] Job D-ID berhasil dibuat (ID: {talk_id}). Menunggu rendering video...")

        # Step 3: Polling D-ID hingga video selesai (maks 15 detik)
        poll_url = f"https://api.d-id.com/talks/{talk_id}"
        video_url = None
        max_polls = 15

        for _ in range(max_polls):
            time.sleep(2)
            status_res, _, _ = make_did_request("GET", poll_url)

            job_status = status_res.get("status")
            print(f"[AI Avatar Polling] Status D-ID: {job_status}")

            if job_status == "done":
                video_url = status_res.get("result_url")
                break
            elif job_status == "error":
                return jsonify({
                    "status": "error",
                    "message": "D-ID gagal memproses video animasi.",
                    "details": status_res
                }), 500

        if not video_url:
            return jsonify({
                "status": "error",
                "message": "Waktu tunggu rendering video habis (timeout)."
            }), 504

        return jsonify({
            "status": "success",
            "prompt": user_prompt,
            "text_response": ai_text_response,
            "video_url": video_url,
            "avatar_image": get_avatar_image_url(),
            "key_index_used": key_idx
        }), 200

    except Exception as e:
        print(f"[AI Avatar Error] Exception: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# --- ENDPOINT WEBRTC STREAMING (UNITS STREAMING REALTIME) ---
@avatar_bp.route('/api/avatar/stream/create', methods=['POST'])
def create_stream():
    """Membuat WebRTC Stream Session baru di D-ID"""
    try:
        payload = {
            "source_url": get_avatar_image_url()
        }
        res, status_code, key_idx = make_did_request("POST", "https://api.d-id.com/talks/streams", payload)
        res["key_index_used"] = key_idx
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@avatar_bp.route('/api/avatar/stream/sdp', methods=['POST'])
def submit_sdp():
    """Mengirim SDP Answer dari client ke D-ID Stream"""
    try:
        data = request.get_json() or {}
        stream_id = data.get('stream_id')
        answer = data.get('answer')
        session_id = data.get('session_id')

        url = f"https://api.d-id.com/talks/streams/{stream_id}/sdp"
        payload = {"answer": answer, "session_id": session_id}
        res, status_code, _ = make_did_request("POST", url, payload)
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@avatar_bp.route('/api/avatar/stream/ice', methods=['POST'])
def submit_ice():
    """Mengirim ICE Candidate dari client ke D-ID Stream"""
    try:
        data = request.get_json() or {}
        stream_id = data.get('stream_id')
        candidate = data.get('candidate')
        session_id = data.get('session_id')

        url = f"https://api.d-id.com/talks/streams/{stream_id}/ice"
        payload = {"candidate": candidate, "session_id": session_id}
        res, status_code, _ = make_did_request("POST", url, payload)
        return jsonify(res), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@avatar_bp.route('/api/avatar/talk/<talk_id>', methods=['GET'])
def get_talk_status(talk_id):
    """Mengecek status rendering video D-ID berdasarkan talk_id"""
    try:
        poll_url = f"https://api.d-id.com/talks/{talk_id}"
        status_res, status_code, _ = make_did_request("GET", poll_url)
        return jsonify(status_res), status_code
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
