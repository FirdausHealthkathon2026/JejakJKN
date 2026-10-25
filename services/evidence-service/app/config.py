"""Environment settings for evidence-service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    evidence_database_url: str = "postgresql+asyncpg://evidence_app:dev_evidence_pass@postgres:5432/evidence_db"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    keycloak_issuer_url: str = "http://localhost:8081/realms/jejakjkn-dev"
    keycloak_jwks_url: str = "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/certs"
    jwt_audience: str = "jejakjkn-api"
    field_encryption_master_key: str = Field(min_length=64)
    patient_response_window_hours: int = Field(default=72, ge=1, le=720)


@lru_cache
def get_settings() -> Settings:
    return Settings()
