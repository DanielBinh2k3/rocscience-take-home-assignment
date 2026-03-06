from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str
    openai_model: str = "gpt-4o-mini"

    # Database
    database_url: str  # asyncpg: postgresql+asyncpg://user:pass@host/db

    # App
    app_name: str = "AI Chat Service"
    debug: bool = False


settings = Settings()
