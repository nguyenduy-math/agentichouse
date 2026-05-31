from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Active LLM provider: "gemini" | "siliconflow"
    llm_provider: str = "gemini"

    # Gemini (google-genai)
    gemini_api_key: str = ""
    gemini_llm_model: str = "gemini-2.5-flash"

    # SiliconFlow (OpenAI-compatible)
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_llm_model: str = "Qwen/Qwen2.5-72B-Instruct"

    session_ttl_minutes: int = 60


settings = Settings()
