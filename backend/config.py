import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from database.shop_db.db import get_db_path


@dataclass(frozen=True)
class Settings:
    db_path: str
    llm_provider: str = "fake"
    model_id: str = "gemini-3.5-flash-lite"
    api_key: str = ""
    llm_timeout: float = 12
    llm_max_retries: int = 0
    llm_daily_limit: int = 500
    llm_usage_path: str | None = None
    session_ttl: int = 86400
    request_limit: int = 120
    chat_limit: int = 10
    session_limit: int = 20

    @classmethod
    # Đọc cấu hình từ .env/biến môi trường và kiểm tra key, timeout, retry cùng các giới hạn.
    def from_env(cls):
        load_dotenv()
        settings = cls(
            db_path=get_db_path(),
            llm_provider=os.getenv("LLM_PROVIDER", "fake"),
            model_id=os.getenv("LLM_MODEL_ID", "gemini-3.5-flash-lite"),
            api_key=os.getenv("GEMINI_API_KEY", ""),
            llm_timeout=float(os.getenv("LLM_TIMEOUT_SECONDS", "12")),
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "0")),
            llm_daily_limit=int(os.getenv("LLM_DAILY_REQUEST_LIMIT", "500")),
            llm_usage_path=os.getenv("LLM_USAGE_DB_PATH", str(Path(__file__).resolve().parents[1] / "database/data/llm_usage.db")),
            session_ttl=int(os.getenv("SESSION_TTL_SECONDS", "86400")),
            request_limit=int(os.getenv("API_REQUESTS_PER_MINUTE", "120")),
            chat_limit=int(os.getenv("CHAT_REQUESTS_PER_MINUTE", "10")),
            session_limit=int(os.getenv("SESSION_REQUESTS_PER_MINUTE", "20")),
        )
        if settings.llm_provider not in {"fake", "gemini"}:
            raise ValueError("LLM_PROVIDER phải là fake hoặc gemini")
        if settings.llm_provider == "gemini" and not settings.api_key:
            raise ValueError("Chưa cấu hình GEMINI_API_KEY trong .env")
        if not 1 <= settings.llm_timeout <= 30 or not 0 <= settings.llm_max_retries <= 2:
            raise ValueError("Timeout phải từ 1-30 giây, retry từ 0-2")
        maximum = 500 if settings.model_id == "gemini-3.5-flash-lite" else 20
        if not 0 <= settings.llm_daily_limit <= maximum:
            raise ValueError(f"Giới hạn gọi {settings.model_id} mỗi ngày phải từ 0-{maximum}")
        if min(settings.session_ttl, settings.request_limit, settings.chat_limit, settings.session_limit) < 1:
            raise ValueError("TTL và giới hạn request phải lớn hơn 0")
        return settings
