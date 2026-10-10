from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./dev.db"
    jwt_secret: str = "dev-secret-change-me-dev-secret-change-me"
    jwt_hours: int = 72
    openai_api_key: str = ""
    openai_base_url: str | None = None
    cors_origins: str = "http://localhost:3000"
    bale_shared_bot_token: str = ""
    global_daily_runs: int = 300        # agent runs per 24h across ALL users (protects the OpenAI budget)
    global_daily_imports: int = 300     # AI-assisted catalog imports per 24h across all users
    register_per_ip_hour: int = 8       # new accounts per IP per hour
    public_base_url: str = ""  # e.g. https://botyar.mahdidev.ir; empty in local dev (no webhooks registered)
    # Telegram is unreachable from Iranian servers, so every Telegram call (and every incoming update) goes through a
    # small reverse proxy outside Iran (relay/main.ts on Deno Deploy). Empty relay URL = Telegram disabled.
    telegram_relay_url: str = ""   # e.g. https://botyar-relay.<org>.deno.net
    telegram_relay_key: str = ""   # shared secret: the relay refuses calls without it
    telegram_shared_bot_token: str = ""
    billing_demo: bool = True  # demo app: «upgrading» simulates a successful payment and activates the plan at once (no money moves)
    admin_usernames: str = ""  # comma-separated usernames that may approve plan upgrade requests (BILLING_DEMO=false)


settings = Settings()
