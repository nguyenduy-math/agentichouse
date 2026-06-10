"""Configuration settings for the Ticket MCP Server."""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


@dataclass
class Settings:
    db_path:          str = field(default_factory=lambda: os.getenv("TICKET_DB_PATH", "./data/tickets.db"))
    default_priority: str = field(default_factory=lambda: os.getenv("TICKET_DEFAULT_PRIORITY", "normal"))
    default_timezone: str = field(default_factory=lambda: os.getenv("DEFAULT_TIMEZONE", "Asia/Ho_Chi_Minh"))

    def __post_init__(self) -> None:
        # Ensure parent directory for db_path exists
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(db_dir, exist_ok=True)


settings = Settings()
