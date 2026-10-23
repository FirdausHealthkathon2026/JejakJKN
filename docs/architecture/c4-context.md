# C4_CONTEXT_AND_CONTAINERS :: v1.0

## 1. SYSTEM_CONTEXT (LEVEL 1)

```mermaid
flowchart LR
  PAT["Patient Simulator App (PWA)\n[React/TS :5173]"]
  SIM_A["SIMRS-A Simulator\n[Web :5174 + Backend :8101]"]
  SIM_B["SIMRS-B Simulator\n[Web :5176 + Backend :8102]"]
  VER["Verifier Portal Simulator\n[React/TS :5175]"]
  KC["Keycloak OIDC\n[jejakjkn-dev :8081]"]
  GW["API Gateway\n[Nginx/Traefik :8080]"]
  CORE["JejakJKN Core Platform\n[4 Microservices + Narrative Worker]"]

  PAT -->|HTTPS /api/v1/patient/*| GW
  SIM_A -->|Client Credentials /api/v1/integrations/*| GW
  SIM_B -->|Client Credentials /api/v1/integrations/*| GW
  VER -->|HTTPS /api/v1/verifications & /review-cases| GW
  KC -.->|OIDC PKCE / Client Credentials| PAT & SIM_A & SIM_B & VER
  GW -->|JWT Validated + Forwarded| CORE
```

## 2. CONTAINER_ISOLATION_RULES

1. `simrs-a-backend` (`simrs_a_db`) and `simrs-b-backend` (`simrs_b_db`) store their own clinical records first and dispatch via `adapters/simrs-a` and `adapters/simrs-b` to `api-gateway`.
2. `encounter-service`, `evidence-service`, `verification-service`, and `review-service` communicate synchronously only via `/internal/v1/*` with `internal_service` JWT audience and asynchronously via RabbitMQ topic exchange `jejakjkn.domain.v1`.
3. No service shares database credentials or tables with any other service.
