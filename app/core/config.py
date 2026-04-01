from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    APP_NAME: str = "CasAI Provenance Lab"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # Storage (legacy file-based, kept for migration path)
    RUNS_DIR: str = "./data/runs"
    EXPORTS_DIR: str = "./data/exports"
    BENCHMARKS_DIR: str = "./data/benchmarks"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/casai.db"
    DB_ECHO: bool = False  # set True to log SQL

    # Auth — JWT
    JWT_SECRET_KEY: str = "change-me-in-production-use-32-char-min"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Auth — API keys
    API_KEY_PREFIX: str = "casai_"
    API_KEY_LENGTH: int = 32          # bytes of entropy (hex → 64 chars)
    API_KEY_HASH_ROUNDS: int = 12     # bcrypt rounds

    # Rate limiting (requests per minute per key)
    RATE_LIMIT_DEFAULT: int = 60
    RATE_LIMIT_BURST: int = 10

    # ML scoring
    SCORING_TIMEOUT_SECONDS: float = 30.0
    MOCK_ML: bool = True              # flip to False when real models are wired
    CFD_MODEL_PATH: str = "./models/cfd_v1.pkl"
    MIT_MODEL_PATH: str = "./models/mit_v1.pkl"
    DEEP_CRISPR_MODEL_PATH: str = "./models/deep_crispr_v1.pt"

    # Default track
    DEFAULT_TRACK: Literal["therapeutic", "crop_demo", "genomics_research"] = "genomics_research"

    # Git/environment (populated at startup)
    GIT_SHA: str = "unknown"
    DOCKER_IMAGE: str = "casai-provenance-lab:1.0.0"

    class Config:
        env_file = ".env"


settings = Settings()

