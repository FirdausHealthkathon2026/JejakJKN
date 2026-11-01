"""FastAPI deny-by-default authentication dependencies."""

from collections.abc import Callable

import jwt
from fastapi import Depends, Header

from jejakjkn_canonical.problems import Problem

from .jwt_verifier import Principal, get_verifier


def principal_dependency(issuer: str, audience: str, jwks_url: str | None = None) -> Callable[..., Principal]:
    def current_principal(authorization: str | None = Header(default=None)) -> Principal:
        if not authorization or not authorization.startswith("Bearer "):
            raise Problem(401, "AUTHENTICATION_REQUIRED", "Authentication required", "A Bearer access token is required.")
        try:
            return get_verifier(issuer, audience, jwks_url).verify(authorization[7:])
        except (jwt.PyJWTError, ValueError) as exc:
            raise Problem(401, "INVALID_ACCESS_TOKEN", "Invalid access token", "The access token could not be verified.") from exc

    return current_principal


def require_roles(current_principal: Callable[..., Principal], *required: str) -> Callable[..., Principal]:
    def guard(principal: Principal = Depends(current_principal)) -> Principal:
        if not principal.roles.intersection(required):
            raise Problem(403, "ROLE_REQUIRED", "Forbidden", "The caller does not have the required role.")
        return principal

    return guard


def require_scopes(current_principal: Callable[..., Principal], *required: str) -> Callable[..., Principal]:
    def guard(principal: Principal = Depends(current_principal)) -> Principal:
        if not set(required).issubset(principal.scopes):
            raise Problem(403, "SCOPE_REQUIRED", "Forbidden", "The caller does not have the required scope.")
        return principal

    return guard
