"""
Configuration management for the SEC Financial Data API.
"""

import os
from pathlib import Path
from typing import List


class Settings:
    """API server configuration."""
    
    # Paths
    BASE_DIR: Path = Path(__file__).parent.parent
    DB_PATH: str = str(BASE_DIR / "data" / "financials.db")
    
    # Server
    API_TITLE: str = "SEC Financial Data API"
    API_DESCRIPTION: str = "REST API for querying SEC EDGAR financial data"
    API_VERSION: str = "1.0.0"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    # CORS
    CORS_ORIGINS: List[str] = ["*"]  # Allow all origins (restrict in production)
    
    # Database
    DB_TIMEOUT: int = 30  # SQLite connection timeout in seconds
    
    # Optional: Rate limiting (not implemented yet)
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_PER_MINUTE: int = 60
    
    # Optional: API Key authentication (not implemented yet)
    API_KEY_ENABLED: bool = False
    API_KEY: str = os.getenv("SEC_API_KEY", "")


settings = Settings()
