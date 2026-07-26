from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Ryu"
    database_url: str = "sqlite+aiosqlite:////data/ryu.db"
    jwt_secret: str = "change-me"
    data_dir: Path = Path("/data")
    workspaces_root: Path = Path("/data/workspaces")
    uploads_dir: Path = Path("/data/uploads")
    allow_signup: bool = True
    dev_verification_code: str | None = None  # se setado, aceita esse código sempre
    litellm_model: str = "anthropic/claude-3-5-haiku-20241022"  # títulos de chat etc.
    port: int = 8000

    model_config = {"env_prefix": "RYU_", "env_file": ".env"}


settings = Settings()
