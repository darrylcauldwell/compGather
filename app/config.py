from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_url: str = "http://equicalendar-ollama:11434"
    ollama_model: str = "qwen2.5:1.5b"
    scan_schedule: str = "06:00"
    scan_interval_minutes: int = 12
    log_level: str = "INFO"
    database_url: str = "sqlite+aiosqlite:///data/equicalendar.db"
    api_key: str = ""
    analytics_domain: str = ""

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = Settings()
