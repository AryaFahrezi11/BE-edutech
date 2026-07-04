import json
from datetime import datetime


def _fmt_dt(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    return str(dt)


class User:
    COLLECTION = "users"

    @staticmethod
    def to_dict(doc: dict):
        return {
            "id": doc.get("id"),
            "nama_lengkap": doc.get("nama_lengkap"),
            "email": doc.get("email"),
            "role": doc.get("role"),
            "is_verified": doc.get("is_verified", False),
            "profile_pict": doc.get("profile_pict"),
            "created_at": _fmt_dt(doc.get("created_at")),
            "updated_at": _fmt_dt(doc.get("updated_at")),
        }


class UserProgress:
    COLLECTION = "user_progress"

    @staticmethod
    def to_dict(doc: dict):
        completed_items = doc.get("completed_items")
        completed_missions = doc.get("completed_missions")

        try:
            items_list = json.loads(completed_items) if completed_items else []
        except Exception:
            items_list = []

        try:
            missions_list = json.loads(completed_missions) if completed_missions else []
        except Exception:
            missions_list = []

        return {
            "total_points": doc.get("total_points", 0),
            "streak_days": doc.get("streak_days", 0),
            "last_login_date": doc.get("last_login_date"),
            "completed_items": items_list,
            "unlocked_writing_letter": doc.get("unlocked_writing_letter", 0),
            "unlocked_writing_lowercase": doc.get("unlocked_writing_lowercase", 0),
            "unlocked_writing_word": doc.get("unlocked_writing_word", 0),
            "unlocked_spelling_letter": doc.get("unlocked_spelling_letter", 0),
            "unlocked_spelling_word": doc.get("unlocked_spelling_word", 0),
            "current_mission_index": doc.get("current_mission_index", 0),
            "completed_missions": missions_list,
        }


class ActivityLog:
    COLLECTION = "activity_logs"

    @staticmethod
    def to_dict(doc: dict):
        return {
            "id": doc.get("id"),
            "user_id": doc.get("user_id"),
            "action": doc.get("action"),
            "description": doc.get("description"),
            "points_earned": doc.get("points_earned", 0),
            "timestamp": _fmt_dt(doc.get("timestamp")),
        }

