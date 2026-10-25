"""Runtime configuration, read from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    sarvam_api_key: SecretStr = SecretStr("")
    sarvam_org_id: str = ""
    sarvam_workspace_id: str = ""
    sarvam_app_id: str = ""
    sarvam_app_version: int = 1
    sarvam_connection_id: str = ""
    sarvam_agent_phone_number: str = ""
    sarvam_base_url: str = "https://apps.sarvam.ai"
    sarvam_use_env_proxy: bool = False

    backend_api_key: SecretStr = SecretStr("")
    public_base_url: str = "http://127.0.0.1:8000"

    db_path: Path = Path("data/rider_agent.db")
    timezone: str = "Asia/Kolkata"
    working_hours_start: int = 9
    working_hours_end: int = 21
    max_unanswered_attempts: int = 3
    retry_backoff_minutes: int = 120
    max_concurrency: int = 5
    stale_dialing_minutes: int = 30

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
