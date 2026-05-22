from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./smartdocmerger.db"
    SECRET_KEY: str = "dev-secret-key-change-in-production-min-32-chars"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    ANTHROPIC_API_KEY: str = ""
    SIMILARITY_THRESHOLD: float = 0.75
    ENVIRONMENT: str = "development"
    ADMIN_EMAIL: str = ""  # set this in .env — this user gets admin access

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
