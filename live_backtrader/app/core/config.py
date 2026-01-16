from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Live Backtrader Platform"
    API_V1_STR: str = "/api/v1"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Database
    DATABASE_URL: str = "sqlite:///./trading_platform.db"  # Use SQLite for initial easy setup as requested
    
    # PocketOption
    POCKET_OPTION_SSID: str = "" # To be loaded from env or DB
    
    class Config:
        env_file = ".env"

settings = Settings()
