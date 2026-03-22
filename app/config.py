from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://trader:password@localhost:5432/traderdb"

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
