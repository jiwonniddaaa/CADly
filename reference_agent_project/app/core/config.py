from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    app_name: str = 'reference-agent'
    app_env: str = 'local'
    anthropic_api_key: str = ''
    anthropic_model: str = 'claude-3-5-sonnet-20241022'
    qdrant_url: str = 'http://localhost:6333'
    qdrant_api_key: str = ''
    qdrant_collection: str = 'architectural_references'
    sqlite_path: str = './data/reference_agent.db'
    raw_storage_path: str = './data/raw'
    text_embed_model: str = 'sentence-transformers/all-MiniLM-L6-v2'
    clip_model: str = 'openai/clip-vit-base-patch32'
    top_k: int = 8

settings = Settings()
