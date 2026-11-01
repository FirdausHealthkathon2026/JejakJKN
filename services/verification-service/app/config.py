"""Environment settings for verification-service."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    verification_database_url: str = "postgresql+asyncpg://verification_app:dev_verification_pass@postgres:5432/verification_db"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    keycloak_issuer_url: str = "http://localhost:8081/realms/jejakjkn-dev"
    keycloak_jwks_url: str = (
        "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/certs"
    )
    keycloak_token_url: str = (
        "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/token"
    )
    jwt_audience: str = "jejakjkn-api"
    internal_client_id: str = "verification-service"
    internal_client_secret: str = "change-me-local-only"
    encounter_service_url: str = "http://encounter-api:8001"
    evidence_service_url: str = "http://evidence-api:8002"
    participant_lookup_hmac_key: str = Field(min_length=64)
    ruleset_version: str = "rules-1.0.0"
    mapping_version: str = "map-v1.0"


@lru_cache
def get_settings() -> Settings:
    return Settings()
