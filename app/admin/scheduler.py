"""
Logika eksekusi scraping otomatis untuk dipanggil oleh Vercel Cron.
(Sebelumnya menggunakan APScheduler).
"""

import datetime
import logging

logger = logging.getLogger(__name__)


def run_daily_scrape_task():
    """
    Fungsi ini dipanggil oleh rute /api/cron/scrape di Vercel Cron.
    Meng-scrape semua aplikasi kompetitor dan menyimpan hasilnya ke MongoDB.
    """
    from app.admin.scraper import scrape_app_reviews
    from app.admin.preprocessing import preprocess_reviews
    from app.admin.playstore_apps import PLAYSTORE_APPS
    from app.extensions import get_db

    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info(f"[VercelCron] Memulai scraping otomatis pada {now_str}")

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
            logger.info(f"[VercelCron] ✅ Berhasil scrape: {app_id}")
        except Exception as e:
            errors[app_id] = str(e)
            logger.warning(f"[VercelCron] ❌ Gagal scrape {app_id}: {e}")

    # Simpan hasil ke MongoDB
    try:
        db = get_db()
        db["competitor_scrapes"].insert_one({
            "timestamp": now_str,
            "scraped_by": "vercel_cron",
            "app_ids": app_ids,
            "results": results,
            "errors": errors,
            "is_auto": True,
        })
        logger.info(
            f"[VercelCron] Selesai. Berhasil: {len(results)}, Gagal: {len(errors)}"
        )
    except Exception as e:
        logger.error(f"[VercelCron] Gagal menyimpan ke DB: {e}")

    return {
        "status": "success",
        "scraped": len(results),
        "failed": len(errors),
        "timestamp": now_str
    }
