"""
Scraper untuk ulasan Google Play Store kompetitor EduTech.
Menggunakan library google-play-scraper.
"""

try:
    from google_play_scraper import reviews as gp_reviews, Sort
    GP_SCRAPER_AVAILABLE = True
except ImportError:
    GP_SCRAPER_AVAILABLE = False

# Daftar aplikasi kompetitor yang tersedia
COMPETITOR_APPS = {
    "com.ayoapps.marbel.alphabetfun": "Marbel - Belajar Membaca",
    "com.duolingo": "Duolingo",
    "org.khanacademy.kids": "Khan Academy Kids",
    "com.ruangguru.app": "Ruangguru",
    "com.lingokids": "Lingokids",
}


def get_competitor_list():
    """Mengembalikan daftar aplikasi kompetitor."""
    return [
        {"app_id": app_id, "name": name}
        for app_id, name in COMPETITOR_APPS.items()
    ]


def scrape_app_reviews(app_id: str, count: int = 50, lang: str = "id", country: str = "id"):
    """
    Mengambil ulasan sebuah aplikasi dari Google Play Store.

    Args:
        app_id: Package name aplikasi (e.g. 'com.duolingo')
        count: Jumlah ulasan yang diambil
        lang: Kode bahasa (default 'id' untuk Indonesia)
        country: Kode negara (default 'id' untuk Indonesia)

    Returns:
        dict dengan app_name, app_id, total_fetched, dan list reviews
    """
    if not GP_SCRAPER_AVAILABLE:
        raise RuntimeError(
            "Library 'google-play-scraper' belum terinstal. "
            "Jalankan: pip install google-play-scraper"
        )

    app_name = COMPETITOR_APPS.get(app_id, app_id)

    # Coba dengan bahasa Indonesia dahulu, fallback ke English jika gagal
    result = []
    for try_lang, try_country in [(lang, country), ("en", "us")]:
        try:
            fetched, _ = gp_reviews(
                app_id,
                lang=try_lang,
                country=try_country,
                sort=Sort.NEWEST,
                count=count,
            )
            result = fetched
            break
        except Exception as e:
            last_error = str(e)
            continue

    if not result:
        raise RuntimeError(f"Gagal mengambil ulasan untuk {app_id}: {last_error}")

    reviews = []
    for r in result:
        reviews.append({
            "username": r.get("userName", "Anonymous"),
            "score": r.get("score", 0),
            "content": (r.get("content") or "").strip(),
            "thumbsUpCount": r.get("thumbsUpCount", 0),
            "at": str(r.get("at", "")),
            "replyContent": (r.get("replyContent") or "").strip(),
        })

    return {
        "app_name": app_name,
        "app_id": app_id,
        "total_fetched": len(reviews),
        "reviews": reviews,
    }
