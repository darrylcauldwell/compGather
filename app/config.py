from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    home_postcode: str = "SW1A 1AA"
    ollama_url: str = "http://compgather-ollama:11434"
    ollama_model: str = "qwen2.5:1.5b"
    scan_schedule: str = "06:00"
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///data/compgather.db"

    @field_validator("home_postcode", mode="before")
    @classmethod
    def default_empty_postcode(cls, v: str) -> str:
        if not v or not v.strip():
            return "SW1A 1AA"
        return v

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
