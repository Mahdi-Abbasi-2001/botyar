from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./dev.db"
    jwt_secret: str = "dev-secret-change-me-dev-secret-change-me"
    jwt_hours: int = 72
    openai_api_key: str = ""
    openai_base_url: str | None = None
    cors_origins: str = "http://localhost:3000"


settings = Settings()
