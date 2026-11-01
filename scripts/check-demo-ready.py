"""Read-only startup checks, executed inside encounter-api with its dependencies."""

import os

import httpx

with httpx.Client(timeout=20) as client:
    for service, port in (
        ("encounter-api", 8001), ("evidence-api", 8002),
        ("verification-api", 8003), ("review-api", 8004),
        ("simrs-a-api", 8101), ("simrs-b-api", 8102),
    ):
        response = client.get(f"http://{service}:{port}/ready")
        response.raise_for_status()
        assert response.json()["status"] == "ready", service

    token_url = "http://keycloak:8080/realms/jejakjkn-dev/protocol/openid-connect/token"
    for client_id, secret_key in (
        ("simrs-a-adapter", "SIMRS_A_CLIENT_SECRET"),
        ("simrs-b-adapter", "SIMRS_B_CLIENT_SECRET"),
        ("verification-service", "VERIFICATION_SERVICE_CLIENT_SECRET"),
        ("review-service", "REVIEW_SERVICE_CLIENT_SECRET"),
    ):
        response = client.post(token_url, data={
            "grant_type": "client_credentials", "client_id": client_id,
            "client_secret": os.environ[secret_key],
        })
        response.raise_for_status()
        assert response.json().get("access_token"), client_id

    for client_id, username, password, endpoint in (
        ("patient-web", "patient01", "synthetic-patient-01", "/patient/encounters?limit=1"),
        ("verifier-web", "verifier01", "synthetic-verifier-01", "/review-cases"),
    ):
        response = client.post(token_url, data={
            "grant_type": "password", "client_id": client_id,
            "username": username, "password": password,
        })
        response.raise_for_status()
        token = response.json()["access_token"]
        client.get(f"http://api-gateway:8080/api/v1{endpoint}",
                   headers={"Authorization": f"Bearer {token}"}).raise_for_status()

    for service, port in (
        ("patient-web", 5173), ("simrs-a-web", 5174),
        ("verifier-web", 5175), ("simrs-b-demo", 5176),
    ):
        client.get(f"http://{service}:{port}",
                   headers={"Host": f"localhost:{port}"}).raise_for_status()

print("Pemeriksaan database, login, API, dan empat portal lulus.")
