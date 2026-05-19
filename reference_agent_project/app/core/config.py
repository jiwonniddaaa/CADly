import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "reference-agent"
    app_env: str = "local"
    
    # Anthropic API 설정
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    
    # GCP Custom Search API 설정
    # GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    # ARCHDAILY_CX: str = os.getenv("ARCHDAILY_CX", "")
    # PINTEREST_CX: str = os.getenv("PINTEREST_CX", "")

    SERPAPI_API_KEY: str = os.getenv("SERPAPI_API_KEY", "")

    class Config:
        env_file = ".env"
        extra = "ignore" # .env에 선언되지 않은 추가 변수가 들어와도 에러 내지 않고 무시함

settings = Settings()