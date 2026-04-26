from __future__ import annotations

from functools import lru_cache
import json
from typing import Any

import requests

from app.config import settings


def llm_is_configured() -> bool:
    provider = settings.llm_provider.lower().strip()
    if provider == "openai":
        return bool(settings.openai_api_key.strip())
    if provider == "gemini":
        return bool(settings.gemini_api_key.strip())
    return False


def llm_source_label() -> str:
    provider = settings.llm_provider.lower().strip()
    if provider == "openai" and llm_is_configured():
        return f"OpenAI {settings.llm_model}"
    if provider == "gemini" and llm_is_configured():
        return f"Gemini {settings.gemini_model}"
    return "Deterministic fallback"


def _openai_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }


def _gemini_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
    }


def _build_prompt(note_payload: dict[str, Any]) -> list[dict[str, str]]:
    system_prompt = (
        "You are a transit heat resilience planning assistant. "
        "Use only the facts in the provided JSON. "
        "Do not invent missing amenities, weather, or ridership facts. "
        "If a field is null or absent, do not mention it. "
        "Return valid JSON with exactly these keys: "
        "reason, recommendation, urgency. "
        "Each of reason and recommendation must be one short sentence. "
        "Urgency must be one of Low, Medium, High, Critical. "
        "Keep the explanation planner-facing and grounded in the inputs."
    )
    user_prompt = (
        "Generate a grounded planner note from this JSON. "
        "Return JSON only.\n\n"
        f"{json.dumps(note_payload, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_structured_prompt(payload: dict[str, Any], system_prompt: str) -> list[dict[str, str]]:
    user_prompt = (
        "Reason only from the provided JSON payload. "
        "Return JSON only.\n\n"
        f"{json.dumps(payload, sort_keys=True)}"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


@lru_cache(maxsize=512)
def _cached_openai_note(payload_signature: str) -> dict[str, Any]:
    response = requests.post(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        headers=_openai_headers(),
        json={
            "model": settings.llm_model,
            "messages": _build_prompt(json.loads(payload_signature)),
            "temperature": 0.2,
            "max_completion_tokens": 220,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "planner_note",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "reason": {"type": "string"},
                            "recommendation": {"type": "string"},
                            "urgency": {
                                "type": "string",
                                "enum": ["Low", "Medium", "High", "Critical"],
                            },
                        },
                        "required": ["reason", "recommendation", "urgency"],
                        "additionalProperties": False,
                    },
                },
            },
        },
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    return json.loads(content)


@lru_cache(maxsize=512)
def _cached_openai_structured(
    payload_signature: str,
    system_prompt: str,
    schema_name: str,
    schema_signature: str,
    temperature: float,
    max_completion_tokens: int,
) -> dict[str, Any]:
    schema = json.loads(schema_signature)
    response = requests.post(
        f"{settings.openai_base_url.rstrip('/')}/chat/completions",
        headers=_openai_headers(),
        json={
            "model": settings.llm_model,
            "messages": _build_structured_prompt(json.loads(payload_signature), system_prompt),
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        },
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    content = payload["choices"][0]["message"]["content"]
    return json.loads(content)


def _with_property_ordering(schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return schema
    schema_copy = {}
    for key, value in schema.items():
        if key == "properties" and isinstance(value, dict):
            schema_copy[key] = {prop: _with_property_ordering(prop_schema) for prop, prop_schema in value.items()}
        elif key == "items" and isinstance(value, dict):
            schema_copy[key] = _with_property_ordering(value)
        else:
            schema_copy[key] = value
    if schema_copy.get("type") == "object" and isinstance(schema_copy.get("properties"), dict):
        schema_copy["propertyOrdering"] = list(schema_copy["properties"].keys())
    return schema_copy


@lru_cache(maxsize=512)
def _cached_gemini_structured(
    payload_signature: str,
    system_prompt: str,
    schema_signature: str,
    temperature: float,
    max_output_tokens: int,
) -> dict[str, Any]:
    schema = _with_property_ordering(json.loads(schema_signature))
    url = (
        f"{settings.gemini_base_url.rstrip('/')}/models/"
        f"{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
    )
    response = requests.post(
        url,
        headers=_gemini_headers(),
        json={
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                "Reason only from the provided JSON payload. "
                                "Return JSON only.\n\n"
                                f"{payload_signature}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
                "responseSchema": schema,
            },
        },
        timeout=settings.llm_timeout_seconds,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(text)


def generate_grounded_planner_note(note_payload: dict[str, Any]) -> dict[str, Any] | None:
    if not llm_is_configured():
        return None

    provider = settings.llm_provider.lower().strip()
    if provider == "openai":
        signature = json.dumps(note_payload, sort_keys=True, separators=(",", ":"))
        try:
            result = _cached_openai_note(signature)
        except Exception:
            return None
    else:
        schema = {
            "type": "object",
            "properties": {
                "reason": {"type": "string"},
                "recommendation": {"type": "string"},
                "urgency": {
                    "type": "string",
                    "enum": ["Low", "Medium", "High", "Critical"],
                },
            },
            "required": ["reason", "recommendation", "urgency"],
            "additionalProperties": False,
        }
        result = generate_grounded_structured_output(
            note_payload,
            system_prompt=(
                "You are a transit heat resilience planning assistant. "
                "Use only the facts in the provided JSON. "
                "Do not invent missing amenities, weather, or ridership facts. "
                "If a field is null or absent, do not mention it. "
                "Return valid JSON with exactly these keys: reason, recommendation, urgency. "
                "Each of reason and recommendation must be one short sentence. "
                "Urgency must be one of Low, Medium, High, Critical. "
                "Keep the explanation planner-facing and grounded in the inputs."
            ),
            schema_name="planner_note",
            schema=schema,
            temperature=0.2,
            max_completion_tokens=220,
        )
        if not result:
            return None

    reason = str(result.get("reason", "")).strip()
    recommendation = str(result.get("recommendation", "")).strip()
    urgency = str(result.get("urgency", "")).strip() or "Medium"
    if not reason or not recommendation:
        return None
    return {
        "reason": reason,
        "recommendation": recommendation,
        "urgency": urgency,
        "source": llm_source_label(),
    }


def generate_grounded_structured_output(
    payload: dict[str, Any],
    *,
    system_prompt: str,
    schema_name: str,
    schema: dict[str, Any],
    temperature: float = 0.2,
    max_completion_tokens: int = 500,
) -> dict[str, Any] | None:
    if not llm_is_configured():
        return None

    payload_signature = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    schema_signature = json.dumps(schema, sort_keys=True, separators=(",", ":"))
    provider = settings.llm_provider.lower().strip()
    try:
        if provider == "openai":
            result = _cached_openai_structured(
                payload_signature,
                system_prompt,
                schema_name,
                schema_signature,
                float(temperature),
                int(max_completion_tokens),
            )
        elif provider == "gemini":
            result = _cached_gemini_structured(
                payload_signature,
                system_prompt,
                schema_signature,
                float(temperature),
                int(max_completion_tokens),
            )
        else:
            return None
    except Exception:
        return None
    if not isinstance(result, dict):
        return None
    result["source"] = llm_source_label()
    return result
