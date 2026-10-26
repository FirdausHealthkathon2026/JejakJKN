"""Keycloak JWT verification and normalized caller identity."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any
from uuid import UUID

import jwt


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    roles: frozenset[str]
    scopes: frozenset[str]
    client_id: str
    organization_id: UUID | None = None
    organization_type: str | None = None
    patient_id: UUID | None = None


class JwtVerifier:
    def __init__(self, issuer: str, audience: str, jwks_url: str | None = None) -> None:
        self.issuer = issuer.rstrip("/")
        self.audience = audience
        self._jwks = jwt.PyJWKClient(jwks_url or f"{self.issuer}/protocol/openid-connect/certs", cache_keys=True)

    def verify(self, token: str) -> Principal:
        signing_key = self._jwks.get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=self.audience,
            issuer=self.issuer,
            options={"require": ["exp", "iat"]},
        )
        subject = str(claims.get("sub") or claims.get("patient_id") or claims.get("org_id") or claims.get("azp") or "unknown")
        return Principal(
            subject=subject,
            roles=frozenset(claims.get("realm_access", {}).get("roles", [])),
            scopes=frozenset(str(claims.get("scope", "")).split()),
            client_id=claims.get("azp", claims.get("client_id", "unknown")),
            organization_id=_uuid_or_none(claims.get("org_id")),
            organization_type=claims.get("org_type"),
            patient_id=_uuid_or_none(claims.get("patient_id")),
        )


def _uuid_or_none(value: Any) -> UUID | None:
    return UUID(str(value)) if value else None


@lru_cache(maxsize=8)
def get_verifier(issuer: str, audience: str, jwks_url: str | None = None) -> JwtVerifier:
    return JwtVerifier(issuer, audience, jwks_url)
