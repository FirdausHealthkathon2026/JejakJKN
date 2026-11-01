# THREAT_MODEL_AND_SECURITY_SPEC :: v1.0

## 1. CRYPTOGRAPHIC_PRIMITIVES

```yaml
crypto:
  participant_blind_index:
    algorithm: "HMAC-SHA256"
    key_env: "PARTICIPANT_LOOKUP_HMAC_KEY"
    input_normalization: "UPPER(TRIM(participant_number))"
  sensitive_column_encryption:
    algorithm: "AES-256-GCM"
    key_env: "FIELD_ENCRYPTION_MASTER_KEY"
    nonce_bytes: 12
    aad_format: "{table_name}:{row_uuid}:{column_name}:v1"
    columns:
      - "encounter_db.patients.participant_number_ciphertext"
      - "encounter_db.patients.display_name_ciphertext"
      - "evidence_db.patient_item_responses.note_ciphertext"
  qr_token_signing:
    algorithm: "EdDSA (Ed25519) or RS256"
    active_kid_env: "QR_SIGNING_ACTIVE_KID"
    ttl_seconds: 60
  audit_hash_chain:
    algorithm: "SHA-256"
    formula: "SHA256(partition_key || ':' || previous_hash || ':' || record_id || ':' || payload_digest || ':' || created_at_iso)"
```

## 2. LOG_REDACTION_FILTER (`libs/python-observability`)

All structured JSON log processors MUST strip or mask values for keys matching:
`(?i)(password|secret|token|qr_token|authorization|participant_number|patient_name|display_name|note|ciphertext|cookie)`
and regex-replace any compact JWS (`eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+`) with `"[REDACTED_JWS]"`.
