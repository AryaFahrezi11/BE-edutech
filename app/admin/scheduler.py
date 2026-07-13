"""
Scheduler otomatis untuk scraping ulasan kompetitor setiap hari.
Menggunakan APScheduler (BackgroundScheduler).
"""

import datetime
import logging
import atexit

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Singleton scheduler
_scheduler: BackgroundScheduler | None = None


def _run_daily_scrape():
    """
    Job yang dijalankan secara otomatis oleh scheduler.
    Meng-scrape semua aplikasi kompetitor dan menyimpan hasilnya ke MongoDB.
    """
    from app.admin.scraper import scrape_app_reviews
    from app.admin.preprocessing import preprocess_reviews
    from app.admin.playstore_apps import PLAYSTORE_APPS
    from app.extensions import get_db

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[AutoScrape] Memulai scraping otomatis pada {now_str}")

    # Kumpulkan semua app_ids dari daftar kompetitor
    app_ids = [data["package"] for data in PLAYSTORE_APPS.values()]

    results = {}
    errors = {}

    for app_id in app_ids:
        try:
            result = scrape_app_reviews(app_id, count=30)
            # Preprocessing
            if "reviews" in result:
                result["analysis"] = preprocess_reviews(result["reviews"])
            results[app_id] = result
            logger.info(f"[AutoScrape] ✅ Berhasil scrape: {app_id}")
        except Exception as e:
            errors[app_id] = str(e)
            logger.warning(f"[AutoScrape] ❌ Gagal scrape {app_id}: {e}")

    # Simpan hasil ke MongoDB
    try:
        db = get_db()
        db["competitor_scrapes"].insert_one({
            "timestamp": now_str,
            "scraped_by": "auto_scheduler",
            "app_ids": app_ids,
            "results": results,
            "errors": errors,
            "is_auto": True,
        })
        logger.info(
            f"[AutoScrape] Selesai. Berhasil: {len(results)}, Gagal: {len(errors)}"
        )
    except Exception as e:
        logger.error(f"[AutoScrape] Gagal menyimpan ke DB: {e}")


def init_scheduler(app):
    """
    Inisialisasi dan jalankan scheduler.
    Dipanggil dari create_app() di __init__.py.

    Scheduler akan menjalankan scraping:
    - Setiap 24 jam (1 hari)
    - Job pertama dijalankan 60 detik setelah server start
      agar server sempat fully initialized terlebih dahulu.
    """
    global _scheduler

    if _scheduler is not None:
        logger.info("[Scheduler] Scheduler sudah berjalan, skip inisialisasi.")
        return

    _scheduler = BackgroundScheduler(daemon=True)

    # Jalankan setiap 24 jam (= 1 hari)
    _scheduler.add_job(
        func=_run_daily_scrape,
        trigger=IntervalTrigger(hours=24),
        id="daily_competitor_scrape",
        name="Daily Competitor Review Scraper",
        replace_existing=True,
        # Job pertama 60 detik dari sekarang agar server siap
        next_run_time=datetime.datetime.now() + datetime.timedelta(seconds=60),
    )

    _scheduler.start()
    logger.info("[Scheduler] ✅ Auto-scrape scheduler aktif (interval: 24 jam)")

    # Matikan scheduler saat app shutdown agar tidak hang
    atexit.register(lambda: _shutdown_scheduler())


def _shutdown_scheduler():
    """Shutdown scheduler dengan aman."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Scheduler dihentikan.")
        _scheduler = None


def get_scheduler_status():
    """
    Mengembalikan status scheduler untuk ditampilkan di dashboard.
    """
    global _scheduler

    if _scheduler is None or not _scheduler.running:
        return {
            "running": False,
            "next_run": None,
            "jobs": [],
        }

    jobs_info = []
    for job in _scheduler.get_jobs():
        jobs_info.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": str(job.next_run_time) if job.next_run_time else None,
        })

    return {
        "running": True,
        "next_run": str(jobs_info[0]["next_run_time"]) if jobs_info else None,
        "jobs": jobs_info,
    }


def trigger_scrape_now():
    """
    Memicu scraping secara manual langsung (tanpa menunggu jadwal).
    Berguna untuk tombol 'Scrape Sekarang' di dashboard.
    """
    global _scheduler
    if _scheduler and _scheduler.running:
        job = _scheduler.get_job("daily_competitor_scrape")
        if job:
            job.modify(next_run_time=datetime.datetime.now())
            return True
    return False
