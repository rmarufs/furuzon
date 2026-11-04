from typing import Any, Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/furuzon"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://localhost:5432/furuzon_test"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    COOKIE_SECURE: bool = False
    SESSION_MAX_AGE_DAYS: int = 30
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    STORAGE_BACKEND: Literal["local", "supabase"] = "local"
    UPLOADS_DIR: str = "uploads"
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    SUPABASE_BUCKET: str = "furuzon"

    MAIL_BACKEND: Literal["console", "smtp"] = "console"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "noreply@furuzon.local"

    @field_validator("SMTP_PORT", mode="before")
    @classmethod
    def parse_empty_port(cls, value: Any) -> Any:
        if value == "" or value is None:
            return 587
        return value

    @model_validator(mode="after")
    def validate_storage_settings(self) -> Self:
        if self.STORAGE_BACKEND == "supabase":
            missing = [
                name
                for name, val in (
                    ("SUPABASE_URL", self.SUPABASE_URL),
                    ("SUPABASE_SERVICE_KEY", self.SUPABASE_SERVICE_KEY),
                    ("SUPABASE_BUCKET", self.SUPABASE_BUCKET),
                )
                if not str(val).strip()
            ]
            if missing:
                vars_list = ", ".join(missing)
                raise ValueError(
                    f"STORAGE_BACKEND=supabase requires {vars_list} to be set"
                )
        return self

    @property
    def is_smtp_configured(self) -> bool:
        return self.MAIL_BACKEND == "smtp" and bool(self.SMTP_HOST.strip())


settings = Settings()
