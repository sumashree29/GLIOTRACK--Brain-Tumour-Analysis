"""Centralised settings — loaded from .env via pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_role_key: str

    r2_endpoint_url: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str = "brain-tumour-scans"

    qdrant_url: str = "https://27936c5e-c463-4f62-9f09-65896af1e8cb.eu-central-1-0.aws.cloud.qdrant.io"
    qdrant_api_key: str = ""
    qdrant_collection_name: str = "clinical_guidelines"

    groq_api_key: str
    modal_webhook_url: str
    modal_status_url: str = ""
    modal_webhook_secret: str = ""

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # FIX #6 — comma-separated allowed origins, never "*"
    allowed_origins: str = "http://localhost:8080"

    # Fix Q4 — trusted reverse-proxy IP; blank = local dev
    trusted_proxy: str = ""

    # Fix R2 — Swagger UI only when DEBUG=true
    debug: bool = False

    # RAG
    rag_min_relevance_score: float = 0.15
    rag_max_passages: int = 5
    chunk_size: int = 1500    
    chunk_overlap: int = 150  

    # ── Agent 2 — RANO classification constants ───────────────────────
    # RANO 2010 §2.1-2.2 — steroid increase defined as > 10 % above baseline
    steroid_increase_threshold: float = 1.10

    # RANO 2010 §2.1 — CR requires ET volume effectively zero (< 0.1 ml)
    cr_et_volume_threshold_ml: float = 0.1

    # RANO 2010 §2.1 — CR_confirmed requires a second qualifying scan
    # at least 4 weeks after the first CR_provisional scan
    cr_confirmation_weeks: int = 4

    # RANO 2010 §2.2 / pseudoprogression literature —
    # PD within 24 weeks of RT completion triggers pseudoprogression flag
    pseudoprogression_rt_weeks: int = 24

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


settings = Settings()