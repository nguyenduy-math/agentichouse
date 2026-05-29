from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gemini_api_key: str
    gemini_llm_model: str = "gemini-2.5-flash"

    session_ttl_minutes: int = 60


settings = Settings()
