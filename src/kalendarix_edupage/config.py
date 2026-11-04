from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # .env and data/ are resolved against the working directory, which the
    # systemd unit pins to the project root.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    edupage_subdomain: str = ""
    edupage_username: str = ""
    edupage_password: str = ""

    kx_host: str = "127.0.0.1"
    kx_port: int = 8787
    kx_token: str = ""
    kx_data_dir: Path = Path("data")
    kx_timezone: str = "Europe/Bratislava"
    kx_sync_interval_min: int = 30
    kx_sync_days_ahead: int = 14

    @property
    def edupage_configured(self) -> bool:
        return bool(
            self.edupage_subdomain and self.edupage_username and self.edupage_password
        )

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.kx_timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()
