from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    simrs_a_database_url: str
    jejakjkn_api_url: str
    keycloak_token_url: str
    simrs_client_id: str
    simrs_client_secret: str
    facility_external_code: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
