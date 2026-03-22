import re
from pydantic_settings import BaseSettings


def _fix_db_url(url: str) -> str:
    """Render gives postgres:// — asyncpg needs postgresql+asyncpg://"""
    url = re.sub(r"^postgres://", "postgresql+asyncpg://", url)
    url = re.sub(r"^postgresql://", "postgresql+asyncpg://", url)
    return url


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://trader:password@localhost:5433/traderdb"

    def __init__(self, **data):
        super().__init__(**data)
        object.__setattr__(self, "DATABASE_URL", _fix_db_url(self.DATABASE_URL))

    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHAT_ID: str = ""

    SYMBOL: str = "BTCUSDT"
    ACCOUNT_BALANCE: float = 10000.0
    MAX_DAILY_LOSS_PCT: float = 0.02
    KELLY_FRACTION: float = 0.25
    CIRCUIT_BREAKER_LOSSES: int = 8

    class Config:
        env_file = ".env"


settings = Settings()
