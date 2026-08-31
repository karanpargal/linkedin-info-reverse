from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    linkedin_li_at: str = ""
    linkedin_jsessionid: str = ""
    linkedin_extra_cookies: str = ""
    api_key: str = ""
    linkedin_min_interval: float = 1.2


@lru_cache
def get_settings() -> Settings:
    return Settings()
