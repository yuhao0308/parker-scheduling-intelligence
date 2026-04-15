from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "postgresql+asyncpg://parker:parker@localhost:5432/parker_scheduling"

    # Ollama (local LLM)
    ollama_model: str = "qwen3.5:9b"
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout: int = 10
    ollama_temperature: float = 0.3

    # Scoring
    scoring_weights_path: Path = Path("config/scoring_weights.yaml")

    # Application
    log_level: str = "INFO"
    max_candidates_returned: int = 10
    shadow_mode: bool = False

    # Facility
    facility_zip_code: str = "11375"

    # Labor compliance
    # NY Labor Law §167 / similar state-level mandatory-OT prohibitions:
    # when enabled, candidates whose acceptance would trigger overtime are
    # eliminated outright to guarantee replacements are voluntary-only.
    voluntary_ot_only: bool = True

    # UKG / WFM write-back (OAuth 2.0 client credentials)
    ukg_base_url: str = ""
    ukg_token_endpoint: str = ""
    ukg_client_id: str = ""
    ukg_client_secret: str = ""
    ukg_write_back_enabled: bool = False


settings = Settings()
