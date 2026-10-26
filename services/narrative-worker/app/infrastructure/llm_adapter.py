"""Optional Hugging Face / DeepSeek model adapter with zero-PII input and deterministic fallback."""

import json
import os
import re
from typing import Any

import httpx

from app.domain.narrator import (
    compute_digest,
    minimize_package,
    narrate,
    validate_narrative,
)

DEFAULT_HF_API_URL = "https://router.huggingface.co/v1/chat/completions"
DEFAULT_HF_MODEL = "deepseek-ai/DeepSeek-V3-0324"
THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

SYSTEM_PROMPT = (
    "Anda adalah asisten penyusun ringkasan faktual untuk verifikator klaim di JejakJKN. "
    "Tugas Anda HANYA mengubah temuan deterministik pada input menjadi narasi Bahasa Indonesia yang netral dan faktual. "
    "ATURAN WAJIB:\n"
    "1. JANGAN PERNAH menyimpulkan 'terbukti fraud', 'pasti fraud', 'definitively fraudulent', atau menentukan keputusan penolakan/pembayaran.\n"
    "2. JANGAN PERNAH menambahkan kode rule baru di luar rule_id yang ada pada daftar 'findings' di input.\n"
    "3. Kembalikan HANYA objek JSON valid dengan tepat 4 kunci bertipe array string: "
    '"summary", "findings", "questions", dan "limitations".\n'
    '4. Setiap elemen dalam "summary", "questions", dan "limitations" minimal 1 kalimat singkat (maksimal 500 karakter per item).'
)


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    cleaned = THINK_PATTERN.sub("", raw_text).strip()
    fence_match = FENCE_PATTERN.search(cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            cleaned = cleaned[start : end + 1]
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("LLM response is not a JSON object")
    return parsed


def get_hf_token() -> str:
    token = (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_API_KEY")
        or os.getenv("LLM_API_KEY")
        or ""
    ).strip()
    if token.startswith("replace-with"):
        return ""
    return token


def is_llm_requested() -> tuple[bool, bool]:
    """Return (should_try_llm, explicitly_requested)."""
    provider = os.getenv("NARRATIVE_PROVIDER", "template").strip().lower()
    token = get_hf_token()
    if provider in {"disabled", "off", "none", "force_template"}:
        return False, False
    if provider in {"huggingface", "hf", "deepseek", "llm", "model"}:
        return bool(token), True
    if provider in {"auto", "template", ""}:
        return bool(token), False
    return False, False


async def generate_narrative(
    package: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> tuple[dict[str, list[str]], str, str, str, str]:
    """Generate narrative using HF LLM when configured, with deterministic fallback.

    Returns:
        (narrative_dict, validation_status, input_digest, method, model_info)
    """
    should_try_llm, explicitly_requested = is_llm_requested()
    model_name = (
        os.getenv("HF_MODEL") or os.getenv("NARRATIVE_MODEL") or DEFAULT_HF_MODEL
    ).strip()
    api_url = (
        os.getenv("HF_API_URL") or os.getenv("NARRATIVE_API_URL") or DEFAULT_HF_API_URL
    ).strip()
    timeout_seconds = float(os.getenv("NARRATIVE_TIMEOUT_SECONDS", "12.0"))

    if not should_try_llm:
        template_result, status, digest = narrate(package)
        if explicitly_requested:
            return (
                template_result,
                "FALLBACK",
                digest,
                "TEMPLATE",
                "deterministic-v1-fallback",
            )
        return template_result, status, digest, "TEMPLATE", "deterministic-v1"

    minimized = minimize_package(package)
    digest = compute_digest(package)
    token = get_hf_token()
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(minimized, ensure_ascii=False, sort_keys=True),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 700,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        if client is not None:
            response = await client.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
        else:
            async with httpx.AsyncClient(timeout=timeout_seconds) as local_client:
                response = await local_client.post(
                    api_url,
                    headers=headers,
                    json=payload,
                )
        response.raise_for_status()
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        candidate = _extract_json_object(content)
        validated, is_valid = validate_narrative(candidate, package)
        if is_valid:
            return (
                validated,
                "VALID",
                digest,
                "LLM",
                f"hf:{model_name}"[:128],
            )
    except Exception:
        pass

    template_result, _, _ = narrate(package)
    return (
        template_result,
        "FALLBACK",
        digest,
        "TEMPLATE",
        "deterministic-v1-fallback",
    )
