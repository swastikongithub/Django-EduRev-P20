"""All settings come from environment variables (or the backend/.env file).

Secrets and machine-specific values never live in the code. See .env.example for every option.
"""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.models.enums import Storage

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql://foodloop:foodloop@localhost:5432/foodloop"
    # Used only by pytest. Must be a separate database whose name ends in "_test" (tests wipe it).
    test_database_url: str = "postgresql://foodloop:foodloop@localhost:5432/foodloop_test"

    # Websites allowed to send state-changing requests (protection against cross-site request forgery).
    allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    cookie_secure: bool = False
    session_days: int = 14

    media_dir: Path = BACKEND_DIR / "media"
    max_upload_mb: int = 5
    # Folder with the built React app (frontend/dist). When set, the API also serves the website.
    frontend_dist: Path | None = None

    reservation_cutoff_minutes: int = 10
    max_active_reservations_per_customer: int = 3
    max_safe_hours_room_temp: float = 2
    max_safe_hours_hot_held: float = 4
    max_safe_hours_refrigerated: float = 24
    max_safe_hours_shelf_stable: float = 48

    login_attempts_per_window: int = 10
    login_window_minutes: int = 15

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("database_url", "test_database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        # People copy URLs like postgres://... from hosting dashboards; SQLAlchemy needs the driver name.
        for prefix in ("postgres://", "postgresql://"):
            if value.startswith(prefix):
                return "postgresql+psycopg://" + value[len(prefix) :]
        return value

    def max_safe_hours(self, storage: Storage) -> float:
        return {
            Storage.room_temp: self.max_safe_hours_room_temp,
            Storage.hot_held: self.max_safe_hours_hot_held,
            Storage.refrigerated: self.max_safe_hours_refrigerated,
            Storage.shelf_stable: self.max_safe_hours_shelf_stable,
        }[storage]


@lru_cache
def get_settings() -> Settings:
    return Settings()
