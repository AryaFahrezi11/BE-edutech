import os
from pymongo import MongoClient


# Mongo handle yang dipakai oleh app/routes.py
client: MongoClient | None = None
_db = None


def init_mongo():
    """Inisialisasi MongoDB dari environment.

    Harus dipanggil sekali saat create_app().
    """
    global client, _db

    mongo_uri = os.getenv("MONGO_URI")
    mongo_db_name = os.getenv("MONGO_DB_NAME")

    if not mongo_uri or not mongo_db_name:
        raise RuntimeError("MONGO_URI dan MONGO_DB_NAME wajib di-set di environment/.env")

    client = MongoClient(mongo_uri)
    _db = client[mongo_db_name]


# Untuk kompatibilitas import: dari app.extensions import db
# db adalah handle Mongo database (bukan SQLAlchemy object).

def get_db():
    global _db
    if _db is None:
        init_mongo()
    return _db

# export name "db" agar kode lama "from app.extensions import db" tetap bekerja.
# Karena name "db" butuh object, kita set ke get_db() saat module diimport.
# create_app() memanggil init_mongo() juga, sehingga aman.
try:
    db = get_db()
except Exception:
    db = None


