from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://app:change_me@localhost:5432/product_intel"
    postgres_db: str = "product_intel"
    postgres_user: str = "app"
    postgres_password: str = "change_me"
    app_env: str = "development"
    log_level: str = "info"

    class Config:
        env_file = "../.env"
        extra = "ignore"

settings = Settings()
