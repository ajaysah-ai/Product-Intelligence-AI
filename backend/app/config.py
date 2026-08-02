from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://app:app_password@db:5432/product_intel"

    # Groq (OpenAI-compatible endpoint)
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # OmniRoute (optional fallback / alternate provider, also OpenAI-compatible)
    omniroute_api_key: str = ""
    omniroute_base_url: str = ""

    # Embeddings (local, no external API needed)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Retrieval
    search_provider: str = "serpapi"
    search_api_key: str = ""
    use_playwright: bool = True

    # App
    app_env: str = "development"
    log_level: str = "info"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()