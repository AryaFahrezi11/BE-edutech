"""
Admin Blueprint — EduTech Dashboard
Semua route admin menggunakan prefix /admin/.
Auth menggunakan Flask session (cookie-based), terpisah dari JWT Flutter.
"""

import os
import json
import datetime
from functools import wraps

import bcrypt
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    session,
    jsonify,
)

from app.extensions import get_db

admin = Blueprint(
    "admin",
    __name__,
    template_folder="templates",
)


# ─────────────────────────────────────────────
#  Helper: decorator proteksi login
# ─────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login"))
        return f(*args, **kwargs)
    return decorated


def _now_str():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ─────────────────────────────────────────────
#  Auth Routes
# ─────────────────────────────────────────────

@admin.route("/login", methods=["GET", "POST"])
def login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin.dashboard"))

    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            error = "Username dan password wajib diisi!"
        else:
            try:
                db = get_db()
                admin_doc = db["admins"].find_one({"username": username})

                if admin_doc:
                    stored_hash = admin_doc.get("password", "")
                    # Support both str and bytes stored hash
                    if isinstance(stored_hash, str):
                        stored_hash = stored_hash.encode("utf-8")

                    if bcrypt.checkpw(password.encode("utf-8"), stored_hash):
                        session["admin_logged_in"] = True
                        session["admin_username"] = username
                        session["admin_login_time"] = _now_str()
                        return redirect(url_for("admin.dashboard"))
                    else:
                        error = "Username atau password salah!"
                else:
                    error = "Username atau password salah!"
            except Exception as e:
                error = f"Terjadi kesalahan: {str(e)}"

    return render_template("admin/login.html", error=error)


@admin.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ─────────────────────────────────────────────
#  Dashboard Page
# ─────────────────────────────────────────────

@admin.route("/dashboard")
@login_required
def dashboard():
    from app.admin.scraper import get_competitor_list
    competitors = get_competitor_list()
    return render_template(
        "admin/dashboard.html",
        admin_username=session.get("admin_username", "Admin"),
        login_time=session.get("admin_login_time", ""),
        competitors=competitors,
    )


# ─────────────────────────────────────────────
#  API: Stats (Total User, Logs, Duration, Active Today)
# ─────────────────────────────────────────────

@admin.route("/api/stats")
@login_required
def api_stats():
    try:
        db = get_db()

        total_users = db["users"].count_documents({"is_verified": True})
        total_all_users = db["users"].count_documents({})
        total_logs = db["activity_logs"].count_documents({})

        # Rata-rata durasi sesi (dalam detik)
        avg_pipeline = [
            {"$match": {"duration_seconds": {"$exists": True, "$ne": None, "$gt": 0}}},
            {"$group": {"_id": None, "avg": {"$avg": "$duration_seconds"}}},
        ]
        avg_result = list(db["app_sessions"].aggregate(avg_pipeline))
        avg_duration_sec = round(avg_result[0]["avg"], 1) if avg_result else 0

        # Pengguna aktif hari ini (ada log hari ini)
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        active_today = db["activity_logs"].count_documents(
            {"timestamp": {"$regex": f"^{today_str}"}}
        )

        # Total sesi
        total_sessions = db["app_sessions"].count_documents({})

        # Pengguna baru minggu ini
        week_ago = (datetime.date.today() - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
        new_this_week = db["users"].count_documents(
            {"created_at": {"$gte": week_ago}}
        )

        return jsonify({
            "total_users": total_users,
            "total_all_users": total_all_users,
            "total_logs": total_logs,
            "avg_duration_seconds": avg_duration_sec,
            "active_today": active_today,
            "total_sessions": total_sessions,
            "new_this_week": new_this_week,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  API: Activity Chart (per jam & per hari)
# ─────────────────────────────────────────────

@admin.route("/api/activity-chart")
@login_required
def api_activity_chart():
    try:
        db = get_db()

        # Ambil semua timestamp dari activity_logs
        logs = list(db["activity_logs"].find({}, {"timestamp": 1, "_id": 0}))

        hour_counts = [0] * 24
        day_counts = [0] * 7   # 0=Senin ... 6=Minggu

        for log in logs:
            ts = log.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.datetime.strptime(str(ts), "%Y-%m-%d %H:%M:%S")
                hour_counts[dt.hour] += 1
                day_counts[dt.weekday()] += 1
            except Exception:
                pass

        # Data tren (30 hari terakhir)
        trend_data = {}
        for log in logs:
            ts = log.get("timestamp")
            if not ts:
                continue
            try:
                day_key = str(ts)[:10]  # "YYYY-MM-DD"
                trend_data[day_key] = trend_data.get(day_key, 0) + 1
            except Exception:
                pass

        # Sort dan ambil 30 hari terakhir
        sorted_days = sorted(trend_data.keys())[-30:]
        
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        trend_labels = []
        for d in sorted_days:
            if d == today_str:
                trend_labels.append(f"{d} (Hari Ini)")
            else:
                trend_labels.append(d)
                
        trend_values = [trend_data[d] for d in sorted_days]

        return jsonify({
            "hourly": {
                "labels": [f"{h:02d}:00" for h in range(24)],
                "data": hour_counts,
            },
            "daily": {
                "labels": ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"],
                "data": day_counts,
            },
            "trend": {
                "labels": trend_labels,
                "data": trend_values,
            },
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  API: Users List
# ─────────────────────────────────────────────

@admin.route("/api/users")
@login_required
def api_users():
    try:
        db = get_db()

        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))
        search = request.args.get("search", "").strip()
        skip = (page - 1) * limit

        query = {}
        if search:
            query = {
                "$or": [
                    {"nama_lengkap": {"$regex": search, "$options": "i"}},
                    {"email": {"$regex": search, "$options": "i"}},
                ]
            }

        total_count = db["users"].count_documents(query)
        users_cursor = (
            db["users"]
            .find(query, {"_id": 0, "password": 0, "otp_code": 0})
            .sort("created_at", -1)
            .skip(skip)
            .limit(limit)
        )
        users = list(users_cursor)

        result = []
        for user in users:
            user_id = user.get("id")
            progress = db["user_progress"].find_one(
                {"user_id": user_id}, {"_id": 0}
            )

            # Hitung total log aktivitas user ini
            log_count = db["activity_logs"].count_documents({"user_id": user_id})

            result.append({
                "id": user_id,
                "nama_lengkap": user.get("nama_lengkap"),
                "email": user.get("email"),
                "role": user.get("role"),
                "is_verified": user.get("is_verified", False),
                "created_at": user.get("created_at"),
                "profile_pict": user.get("profile_pict"),
                "total_points": progress.get("total_points", 0) if progress else 0,
                "streak_days": progress.get("streak_days", 0) if progress else 0,
                "activity_count": log_count,
            })

        return jsonify({
            "users": result,
            "total": total_count,
            "page": page,
            "limit": limit,
            "total_pages": (total_count + limit - 1) // limit,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  API: Scrape Competitor Reviews
# ─────────────────────────────────────────────

@admin.route("/api/scrape", methods=["POST"])
@login_required
def api_scrape():
    from app.admin.scraper import scrape_app_reviews
    from app.admin.preprocessing import preprocess_reviews

    data = request.get_json() or {}
    app_ids = data.get("app_ids", [])

    if not app_ids:
        return jsonify({"error": "app_ids wajib diisi"}), 400

    results = {}
    errors = {}

    for app_id in app_ids:
        try:
            # Mengurangi jumlah ulasan dari 50 menjadi 30 agar lebih cepat diproses
            # di server Render (menghindari timeout)
            result = scrape_app_reviews(app_id, count=100)
            # Preprocessing
            if "reviews" in result:
                result["analysis"] = preprocess_reviews(result["reviews"])
            results[app_id] = result
        except Exception as e:
            errors[app_id] = str(e)

    # Simpan hasil scraping ke DB
    try:
        db = get_db()
        db["competitor_scrapes"].insert_one({
            "timestamp": _now_str(),
            "scraped_by": session.get("admin_username"),
            "app_ids": app_ids,
            "results": results,
            "errors": errors,
        })
    except Exception:
        pass  # Gagal menyimpan ke DB tidak menggagalkan response

    return jsonify({
        "status": "success" if results else "partial",
        "results": results,
        "errors": errors,
    })


@admin.route("/api/latest-scrape", methods=["GET"])
@login_required
def api_latest_scrape():
    try:
        db = get_db()
        # Cari data scraping terakhir
        latest = db["competitor_scrapes"].find_one(
            {}, sort=[("timestamp", -1)]
        )
        if latest:
            # Hapus _id agar bisa di-serialize ke JSON
            latest.pop("_id", None)
            return jsonify({
                "status": "success",
                "data": latest
            })
        return jsonify({"status": "empty", "data": None})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  API: AI Analysis (Gemini)
# ─────────────────────────────────────────────

@admin.route("/api/ai-analysis", methods=["POST"])
@login_required
def api_ai_analysis():
    data = request.get_json() or {}
    reviews_data = data.get("reviews_data", {})

    if not reviews_data:
        return jsonify({"error": "reviews_data wajib diisi"}), 400

    # Susun teks ulasan untuk Gemini
    reviews_text = ""
    for app_id, app_data in reviews_data.items():
        if not isinstance(app_data, dict):
            continue
        if "error" in app_data:
            continue
        app_name = app_data.get("app_name", app_id)
        reviews = app_data.get("reviews", [])

        # Hitung statistik rating
        scores = [r.get("score", 0) for r in reviews if r.get("score")]
        avg_score = round(sum(scores) / len(scores), 2) if scores else 0

        reviews_text += f"\n\n=== {app_name} (Rating rata-rata: {avg_score}⭐) ===\n"
        for r in reviews[:25]:  # max 25 ulasan per app
            score = r.get("score", 0)
            content = (r.get("content") or "").strip()
            if content:
                reviews_text += f"- [{score}⭐] {content[:250]}\n"

    if not reviews_text.strip():
        return jsonify({"error": "Tidak ada ulasan yang dapat dianalisis"}), 400

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        return jsonify({"error": "GEMINI_API_KEY tidak ditemukan di environment"}), 500

    try:
        from google import genai

        client = genai.Client(api_key=gemini_key)

        prompt = f"""Anda adalah Senior Product Consultant yang menganalisis ulasan Google Play Store aplikasi kompetitor.

        Berdasarkan ulasan yang diberikan, buat analisis yang singkat, padat, dan langsung ke inti.

        Aturan:
        - Gunakan Bahasa Indonesia yang profesional.
        - Maksimal 250 kata.
        - Jangan membuat paragraf panjang.
        - Gunakan bullet point.
        - Jangan menjelaskan terlalu detail.
        - Jangan mengulang informasi.
        - Fokus pada insight yang paling penting.

        Format jawaban WAJIB seperti berikut:

        📊 Analisis Kompetitor

        ❌ Kekurangan Utama
        - Maksimal 5 poin.
        - Hanya tuliskan kekurangan yang paling sering muncul.

        💡 Rekomendasi untuk EduTech
        - Maksimal 5 poin.
        - Berikan rekomendasi yang konkret dan dapat diterapkan.

        🚀 Peluang Diferensiasi
        - Maksimal 3 poin.
        - Jelaskan peluang agar EduTech lebih unggul dari kompetitor.

        ⭐ Kesimpulan
        - Maksimal 2 kalimat.
        - Ringkas dan langsung pada inti.

        Jangan menambahkan pembukaan, penutup, disclaimer, atau penjelasan lain di luar format tersebut."""

        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=[prompt]
        )
        analysis_text = response.text or "Gagal mendapatkan analisis dari AI."

        # Simpan hasil analisis ke DB
        try:
            db = get_db()
            db["ai_analyses"].insert_one({
                "timestamp": _now_str(),
                "analyzed_by": session.get("admin_username"),
                "apps_analyzed": list(reviews_data.keys()),
                "analysis": analysis_text,
            })
        except Exception:
            pass

        return jsonify({
            "status": "success",
            "analysis": analysis_text,
            "timestamp": _now_str(),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  API: Recent Activity Logs
# ─────────────────────────────────────────────

@admin.route("/api/recent-logs")
@login_required
def api_recent_logs():
    try:
        db = get_db()
        limit = int(request.args.get("limit", 10))

        pipeline = [
            {"$sort": {"timestamp": -1}},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": "users",
                    "localField": "user_id",
                    "foreignField": "id",
                    "as": "user",
                }
            },
            {"$unwind": {"path": "$user", "preserveNullAndEmptyArrays": True}},
            {
                "$project": {
                    "_id": 0,
                    "user_id": 1,
                    "action": 1,
                    "description": 1,
                    "points_earned": 1,
                    "timestamp": 1,
                    "nama_lengkap": "$user.nama_lengkap",
                    "email": "$user.email",
                }
            },
        ]

        logs = list(db["activity_logs"].aggregate(pipeline))
        return jsonify({"logs": logs})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  API: Previous AI Analyses
# ─────────────────────────────────────────────

@admin.route("/api/analyses-history")
@login_required
def api_analyses_history():
    try:
        db = get_db()
        analyses = list(
            db["ai_analyses"]
            .find({}, {"_id": 0, "analysis": 0})
            .sort("timestamp", -1)
            .limit(10)
        )
        return jsonify({"analyses": analyses})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
#  API: Auto-Scrape Scheduler
# ─────────────────────────────────────────────

@admin.route("/api/scheduler-status")
@login_required
def api_scheduler_status():
    """Mengembalikan status scheduler (kini menggunakan Vercel Cron)."""
    try:
        # Vercel Cron dikonfigurasi melalui vercel.json, 
        # kita kembalikan status statis untuk dashboard.
        status = {
            "running": True, 
            "next_run": "Diatur oleh Vercel Cron",
            "jobs": [{"id": "vercel_cron", "name": "Vercel Cron Auto-Scrape", "next_run_time": "Diatur oleh Vercel Cron"}]
        }

        # Tambahkan info scraping terakhir dari DB
        db = get_db()
        last_auto = db["competitor_scrapes"].find_one(
            {"is_auto": True}, sort=[("timestamp", -1)]
        )
        if last_auto:
            last_auto.pop("_id", None)
            status["last_auto_scrape"] = last_auto.get("timestamp")
            status["last_auto_apps"] = last_auto.get("app_ids", [])
            status["last_auto_success"] = len(last_auto.get("results", {}))
            status["last_auto_errors"] = len(last_auto.get("errors", {}))
        else:
            status["last_auto_scrape"] = None

        return jsonify({"status": "success", "scheduler": status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@admin.route("/api/trigger-scrape", methods=["POST"])
@login_required
def api_trigger_scrape():
    """Memicu scraping otomatis secara manual dari dashboard."""
    try:
        from app.admin.scheduler import run_daily_scrape_task
        result = run_daily_scrape_task()
        return jsonify({
            "status": "success",
            "message": "Scraping berhasil dijalankan secara manual.",
            "data": result
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
        
@admin.route("/api/cron/scrape", methods=["GET", "POST"])
def api_cron_scrape():
    """
    Rute yang dipanggil oleh Vercel Cron untuk menjalankan auto-scrape.
    Dilindungi oleh CRON_SECRET dari environment variable.
    """
    auth_header = request.headers.get("Authorization")
    expected_secret = os.getenv("CRON_SECRET")
    
    if expected_secret:
        if auth_header != f"Bearer {expected_secret}":
            return jsonify({"error": "Unauthorized"}), 401
            
    from app.admin.scheduler import run_daily_scrape_task
    result = run_daily_scrape_task()
    
    return jsonify(result)


@admin.route("/api/scrape-history")
@login_required
def api_scrape_history():
    """Mengembalikan riwayat scraping (manual & otomatis) dengan pagination."""
    try:
        db = get_db()
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 10))
        filter_type = request.args.get("type", "all")  # all | auto | manual
        skip = (page - 1) * limit

        query = {}
        if filter_type == "auto":
            query["is_auto"] = True
        elif filter_type == "manual":
            query["$or"] = [{"is_auto": {"$exists": False}}, {"is_auto": False}]

        total = db["competitor_scrapes"].count_documents(query)
        scrapes = list(
            db["competitor_scrapes"]
            .find(query, {"_id": 0, "results": 0})  # Exclude heavy data
            .sort("timestamp", -1)
            .skip(skip)
            .limit(limit)
        )

        return jsonify({
            "status": "success",
            "scrapes": scrapes,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

