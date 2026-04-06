"""Supabase client singleton."""
from supabase import create_client, Client
from app.core.config import settings
import functools

@functools.lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_role_key)
