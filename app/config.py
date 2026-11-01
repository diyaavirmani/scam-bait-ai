"""Settings read from the environment (and .env). Names only; values never logged."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()

REQUIRED_FOR_RUNTIME = ("OPENAI_API_KEY", "CEREBRAS_API_KEY")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    return int(raw) if raw.isdigit() else default


@dataclass(frozen=True)
class Settings:
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    cerebras_api_key: str = field(default_factory=lambda: os.getenv("CEREBRAS_API_KEY", ""))
    cerebras_base_url: str = "https://api.cerebras.ai/v1"
    cerebras_rpm_oss: int = field(default_factory=lambda: _int("CEREBRAS_RPM_OSS", 5))
    cerebras_rpm_qwen: int = field(default_factory=lambda: _int("CEREBRAS_RPM_QWEN", 5))
    persona_model: str = field(default_factory=lambda: os.getenv("PERSONA_MODEL", "gpt-oss-120b"))
    flag_model: str = field(default_factory=lambda: os.getenv("FLAG_MODEL", "qwen-3.8-27b"))
    decisions_model: str = field(default_factory=lambda: os.getenv("DECISIONS_MODEL", "gpt-6-luna"))
    live_model: str = field(default_factory=lambda: os.getenv("LIVE_MODEL", "gpt-live-1"))
    twilio_account_sid: str = field(default_factory=lambda: os.getenv("TWILIO_ACCOUNT_SID", ""))
    twilio_auth_token: str = field(default_factory=lambda: os.getenv("TWILIO_AUTH_TOKEN", ""))
    twilio_phone_number: str = field(default_factory=lambda: os.getenv("TWILIO_PHONE_NUMBER", ""))
    public_base_url: str = field(default_factory=lambda: os.getenv("PUBLIC_BASE_URL", "").rstrip("/"))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_webhook_secret: str = field(default_factory=lambda: os.getenv("TELEGRAM_WEBHOOK_SECRET", ""))
    api_key: str = field(default_factory=lambda: os.getenv("API_KEY", ""))
    demo_mode: bool = field(default_factory=lambda: os.getenv("DEMO_MODE", "0") == "1")
    call_batch_seconds: int = field(default_factory=lambda: _int("CALL_BATCH_SECONDS", 20))
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", "scambait.db"))

    def missing_required(self) -> list[str]:
        """Names of required settings that are empty (values are never returned)."""
        return [name for name in REQUIRED_FOR_RUNTIME if not os.getenv(name, "").strip()]


def get_settings() -> Settings:
    return Settings()
