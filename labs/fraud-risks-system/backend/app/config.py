from __future__ import annotations

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    gemini_api_key: str
    gemini_llm_model: str = "gemini-2.5-flash"

    database_url: str = "postgresql+asyncpg://fraud:fraud-secret@localhost:5432/fraud_detection"

    batch_cron_hour: int = 2
    batch_cron_minute: int = 0
    batch_max_claims: int = 500

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_username: str = "neo4j"
    neo4j_password: str = "fraud-neo4j-secret"

    llm_score_weight: float = 0.7
    rule_score_weight: float = 0.3
    ml_score_weight: float = 0.3

    ml_min_samples: int = 20
    ml_model_path: str = "models/xgboost_fraud.pkl"
    ml_auto_train: bool = True

    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]


settings = Settings()
