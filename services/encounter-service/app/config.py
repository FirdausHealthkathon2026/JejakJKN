"""Environment-backed configuration for encounter-service."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    encounter_database_url: str = "postgresql+asyncpg://encounter_app:dev_encounter_pass@postgres:5432/encounter_db"
    redis_url: str = "redis://redis:6379/0"
    keycloak_issuer_url: str = "http://localhost:8081/realms/jejakjkn-dev"
    keycloak_jwks_url: str = "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/certs"
    jwt_audience: str = "jejakjkn-api"
    qr_token_ttl_seconds: int = Field(default=60, ge=30, le=120)
    qr_signing_private_key_path: Path = Path("/run/secrets/qr-signing-private.pem")
    qr_signing_public_key_path: Path = Path("/run/secrets/qr-signing-public.pem")
    qr_signing_kid: str = "dev-ed25519-1"
    participant_lookup_hmac_key: str = Field(min_length=64)
    field_encryption_master_key: str = Field(min_length=64)


@lru_cache
def get_settings() -> Settings:
    return Settings()
