from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    review_database_url: str = (
        "postgresql+asyncpg://review_app:dev_review_pass@postgres:5432/review_db"
    )
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    keycloak_issuer_url: str = "http://localhost:8081/realms/jejakjkn-dev"
    keycloak_jwks_url: str = (
        "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/certs"
    )
    keycloak_token_url: str = (
        "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/token"
    )
    jwt_audience: str = "jejakjkn-api"
    internal_client_id: str = "review-service"
    internal_client_secret: str = "change-me-local-only"
    verification_service_url: str = "http://verification-api:8003"


@lru_cache
def get_settings() -> Settings:
    return Settings()
