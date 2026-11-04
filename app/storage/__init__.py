from app.core.config import settings
from app.storage.base import Storage
from app.storage.local import LocalStorage
from app.storage.supabase import SupabaseStorage


def get_storage() -> Storage:
    if settings.STORAGE_BACKEND == "supabase":
        return SupabaseStorage(
            url=settings.SUPABASE_URL,
            service_key=settings.SUPABASE_SERVICE_KEY,
            bucket=settings.SUPABASE_BUCKET,
        )
    return LocalStorage(settings.UPLOADS_DIR)


__all__ = ["LocalStorage", "Storage", "SupabaseStorage", "get_storage"]
