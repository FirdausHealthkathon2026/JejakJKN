"""Recursive log-field redaction; request bodies are deliberately never logged."""

import re
from typing import Any

SENSITIVE_KEY = re.compile(r"(?i)(password|secret|token|qr_token|authorization|participant_number|patient_name|display_name|note|ciphertext|cookie)")
COMPACT_JWS = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def redact(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact(item_value, item_key) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return COMPACT_JWS.sub("[REDACTED_JWS]", value)
    return value
