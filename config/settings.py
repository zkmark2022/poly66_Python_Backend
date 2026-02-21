from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database (defaults match docker-compose.yml for local dev)
    DATABASE_URL: str = (
        "postgresql+asyncpg://pm_user:pm_pass@localhost:5432/prediction_market"
    )

    # Redis (defaults match docker-compose.yml for local dev)
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT — no default, MUST be set in .env
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 30

    # App
    APP_NAME: str = "Prediction Market"
    DEBUG: bool = False  # Safe default for production; set DEBUG=True in .env for local dev


settings = Settings()
