from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://app:change_me@localhost:5432/product_intel"
    postgres_db: str = "product_intel"
    postgres_user: str = "app"
    postgres_password: str = "change_me"
    app_env: str = "development"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    groq_base_url: str = "https://api.groq.com/openai/v1"
    omniroute_api_key: str = ""
    omniroute_base_url: str = ""
    log_level: str = "info"

    class Config:
        env_file = "../.env"
        extra = "ignore"

settings = Settings()
