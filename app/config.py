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
    linkedin_proxy: str = ""
    api_key: str = ""
    linkedin_min_interval: float = 3.5
    linkedin_cache_ttl: float = 600.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
