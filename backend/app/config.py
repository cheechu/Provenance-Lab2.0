from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application configuration."""
    
    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@postgres:5432/provenance"
    
    # Prefect
    prefect_api_url: str = "http://prefect-server:4200/api"
    
    # App
    app_name: str = "Provenance Lab API"
    debug: bool = True
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
