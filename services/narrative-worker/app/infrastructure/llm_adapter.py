"""Optional Groq LLM adapter with zero-PII input and deterministic fallback."""

import json
import os
import re
from typing import Any
import urllib.error
import urllib.request

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]

from app.domain.narrator import (
    compute_digest,
    minimize_package,
    narrate,
    validate_narrative,
)

DEFAULT_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_GROQ_MODEL = "qwen/qwen3.8-27b"
THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)

SYSTEM_PROMPT = (
    "Anda adalah asisten penyusun ringkasan faktual untuk verifikator klaim di JejakJKN. "
    "Tugas Anda HANYA mengubah temuan deterministik pada input menjadi narasi Bahasa Indonesia yang netral, lugas, dan eksplisit. "
    "ATURAN WAJIB:\n"
    "1. JANGAN PERNAH menyebut kode placeholder internal seperti 'ITEM-1', 'ITEM-2', 'DX-PRIMARY', 'PROC-1', 'MED-1', atau 'claim_item_ref'. Sebutkan langsung nama tindakan, prosedur, obat, atau layanan medisnya secara eksplisit.\n"
    "2. Pada bagian 'summary', pisahkan dan sebutkan secara eksplisit:\n"
    "   - Kalimat pertama diawali 'YANG SESUAI: ' berisi rincian kunjungan, identitas, dan tindakan/obat apa saja yang terbukti sesuai dengan rekam medis.\n"
    "   - Kalimat kedua diawali 'YANG TIDAK SESUAI: ' berisi rincian tindakan/obat/kondisi apa saja yang tidak sesuai bukti SIMRS, selisih jumlah, atau disanggah pasien.\n"
    "3. JANGAN PERNAH menyimpulkan 'terbukti fraud', 'pasti fraud', 'definitively fraudulent', atau menentukan keputusan penolakan/pembayaran.\n"
    "4. JANGAN PERNAH menambahkan kode rule baru di luar rule_id yang ada pada daftar 'findings' di input.\n"
    "5. Kembalikan HANYA objek JSON valid dengan tepat 4 kunci bertipe array string: "
    '"summary", "findings", "questions", dan "limitations".\n'
    '6. Setiap elemen dalam "summary", "questions", dan "limitations" minimal 1 kalimat singkat (maksimal 500 karakter per item).'
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


def get_groq_api_key() -> str:
    token = (
        os.getenv("GROQ_API_KEY")
        or os.getenv("GROQ_TOKEN")
        or os.getenv("LLM_API_KEY")
        or os.getenv("HF_TOKEN")
        or ""
    ).strip()
    if token.startswith("replace-with"):
        return ""
    return token


# Keep alias for backwards compatibility in tests/imports
get_hf_token = get_groq_api_key


def is_llm_requested() -> tuple[bool, bool]:
    """Return (should_try_llm, explicitly_requested)."""
    provider = os.getenv("NARRATIVE_PROVIDER", "template").strip().lower()
    token = get_groq_api_key()
    if provider in {"disabled", "off", "none", "force_template"}:
        return False, False
    if provider in {"groq", "llm", "model", "deepseek", "huggingface", "hf", "openai"}:
        return bool(token), True
    if provider in {"auto", "template", ""}:
        return bool(token), False
    return bool(token), True


def _build_request(
    package: dict[str, Any],
) -> tuple[str, str, dict[str, str], dict[str, Any], float, str]:
    model_name = (
        os.getenv("GROQ_MODEL")
        or os.getenv("NARRATIVE_MODEL")
        or os.getenv("HF_MODEL")
        or DEFAULT_GROQ_MODEL
    ).strip()
    api_url = (
        os.getenv("GROQ_API_URL")
        or os.getenv("NARRATIVE_API_URL")
        or os.getenv("HF_API_URL")
        or DEFAULT_GROQ_API_URL
    ).strip()
    timeout_seconds = float(os.getenv("NARRATIVE_TIMEOUT_SECONDS", "25.0"))
    minimized = minimize_package(package)
    digest = compute_digest(package)
    token = get_groq_api_key()
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
        "User-Agent": "jejakjkn-narrative-worker/1.0",
    }
    return api_url, model_name, headers, payload, timeout_seconds, digest


def _post_urllib(
    api_url: str,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        if err.code == 404 and "api.groq.com" in api_url:
            models_req = urllib.request.Request(
                "https://api.groq.com/openai/v1/models",
                headers=headers,
                method="GET",
            )
            with urllib.request.urlopen(models_req, timeout=timeout_seconds) as m_resp:
                models_data = json.loads(m_resp.read().decode("utf-8")).get("data", [])
            preferred = [
                m["id"]
                for m in models_data
                if isinstance(m, dict)
                and "id" in m
                and not any(
                    skip in m["id"].lower()
                    for skip in ("whisper", "tts", "guard", "embed", "playai")
                )
            ]
            if preferred:
                fallback_payload = dict(payload, model=preferred[0])
                retry_req = urllib.request.Request(
                    api_url,
                    data=json.dumps(fallback_payload).encode("utf-8"),
                    headers=headers,
                    method="POST",
                )
                with urllib.request.urlopen(retry_req, timeout=timeout_seconds) as resp2:
                    data = json.loads(resp2.read().decode("utf-8"))
                    data["_resolved_model"] = preferred[0]
                    return data
        raise


def _finalize_response(
    body: dict[str, Any],
    package: dict[str, Any],
    digest: str,
    model_name: str,
) -> tuple[dict[str, list[str]], str, str, str, str] | None:
    resolved_model = str(body.get("_resolved_model") or body.get("model") or model_name)
    content = body["choices"][0]["message"]["content"]
    candidate = _extract_json_object(content)
    validated, is_valid = validate_narrative(candidate, package)
    if is_valid:
        return (
            validated,
            "VALID",
            digest,
            "LLM",
            f"groq:{resolved_model}"[:128],
        )
    return None


def generate_narrative_sync(
    package: dict[str, Any],
) -> tuple[dict[str, list[str]], str, str, str, str]:
    """Synchronous narrative generation using urllib (no event-loop socketpair needed)."""
    should_try_llm, explicitly_requested = is_llm_requested()
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

    api_url, model_name, headers, payload, timeout_seconds, digest = _build_request(
        package
    )
    try:
        body = _post_urllib(api_url, headers, payload, timeout_seconds)
        finalized = _finalize_response(body, package, digest, model_name)
        if finalized is not None:
            return finalized
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


async def generate_narrative(
    package: dict[str, Any],
    client: Any = None,
) -> tuple[dict[str, list[str]], str, str, str, str]:
    """Generate narrative using Groq LLM when configured, with deterministic fallback.

    Returns:
        (narrative_dict, validation_status, input_digest, method, model_info)
    """
    should_try_llm, explicitly_requested = is_llm_requested()
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

    api_url, model_name, headers, payload, timeout_seconds, digest = _build_request(
        package
    )

    try:
        if client is not None:
            response = await client.post(
                api_url,
                headers=headers,
                json=payload,
                timeout=timeout_seconds,
            )
            if getattr(response, "status_code", 200) == 404 and "api.groq.com" in api_url:
                m_resp = await client.get(
                    "https://api.groq.com/openai/v1/models",
                    headers=headers,
                    timeout=timeout_seconds,
                )
                m_resp.raise_for_status()
                preferred = [
                    m["id"]
                    for m in m_resp.json().get("data", [])
                    if isinstance(m, dict)
                    and "id" in m
                    and not any(
                        skip in m["id"].lower()
                        for skip in ("whisper", "tts", "guard", "embed", "playai")
                    )
                ]
                if preferred:
                    response = await client.post(
                        api_url,
                        headers=headers,
                        json=dict(payload, model=preferred[0]),
                        timeout=timeout_seconds,
                    )
            response.raise_for_status()
            body = response.json()
        elif httpx is not None:
            async with httpx.AsyncClient(timeout=timeout_seconds) as local_client:
                response = await local_client.post(
                    api_url,
                    headers=headers,
                    json=payload,
                )
                if response.status_code == 404 and "api.groq.com" in api_url:
                    m_resp = await local_client.get(
                        "https://api.groq.com/openai/v1/models",
                        headers=headers,
                    )
                    m_resp.raise_for_status()
                    preferred = [
                        m["id"]
                        for m in m_resp.json().get("data", [])
                        if isinstance(m, dict)
                        and "id" in m
                        and not any(
                            skip in m["id"].lower()
                            for skip in ("whisper", "tts", "guard", "embed", "playai")
                        )
                    ]
                    if preferred:
                        response = await local_client.post(
                            api_url,
                            headers=headers,
                            json=dict(payload, model=preferred[0]),
                        )
                response.raise_for_status()
                body = response.json()
        else:
            body = _post_urllib(api_url, headers, payload, timeout_seconds)
        finalized = _finalize_response(body, package, digest, model_name)
        if finalized is not None:
            return finalized
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
