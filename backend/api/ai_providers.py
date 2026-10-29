"""Server-side suggestion routing with provider failover and an offline fallback."""
from __future__ import annotations

import json
import os
import re
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx

from .discovery import suggest_scope


PostJson = Callable[[str, dict[str, str], dict[str, Any]], Awaitable[dict[str, Any]]]


async def _http_post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=httpx.Timeout(14.0, connect=5.0)) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()


def _providers(environ: dict[str, str]) -> list[tuple[str, str, str]]:
    """Return configured providers as (name, key, model); never return keys to callers."""
    order = [part.strip().lower() for part in environ.get("AI_PROVIDER_ORDER", "openrouter,gemini").split(",")]
    available = {
        "openrouter": (environ.get("OPENROUTER_API_KEY", "").strip(), environ.get("OPENROUTER_MODEL", "openrouter/free").strip()),
        "gemini": (environ.get("GEMINI_API_KEY", "").strip(), environ.get("GEMINI_MODEL", "").strip()),
    }
    configured: list[tuple[str, str, str]] = []
    for provider in order:
        if provider not in available:
            continue
        key, model = available[provider]
        if key and model:
            configured.append((provider, key, model))
    return configured


def configured_provider_names(environ: dict[str, str] | None = None) -> list[str]:
    return [name for name, _, _ in _providers(environ or os.environ)]


def _json_text(provider: str, response: dict[str, Any]) -> str:
    if provider == "openrouter":
        content = response["choices"][0]["message"]["content"]
        if isinstance(content, list):
            return "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return str(content)
    parts = response["candidates"][0]["content"]["parts"]
    return "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))


def _parse_json(text: str) -> dict[str, Any]:
    clean = text.strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.IGNORECASE)
    result = json.loads(clean)
    if not isinstance(result, dict):
        raise ValueError("The provider response was not an object.")
    return result


def _strings(value: Any, fallback: list[str], maximum: int, max_length: int = 120) -> list[str]:
    if not isinstance(value, list):
        value = fallback
    cleaned: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = " ".join(item.split())[:max_length]
        if text and text.casefold() not in {v.casefold() for v in cleaned}:
            cleaned.append(text)
        if len(cleaned) >= maximum:
            break
    return cleaned or fallback[:maximum]


def _normalise(value: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    family = value.get("category_family")
    if not isinstance(family, str) or not family.strip():
        family = fallback["category_family"]
    return {
        "category_family": " ".join(family.split())[:100],
        "summary": fallback["summary"],
        "suggested_segments": _strings(value.get("suggested_segments"), fallback["suggested_segments"], 8),
        "comparison_attributes": _strings(value.get("comparison_attributes"), fallback["comparison_attributes"], 10),
        "search_phrases": _strings(value.get("search_phrases"), fallback["search_phrases"], 10),
        "research_angles": fallback["research_angles"],
        "confidence": "AI suggestions; review before scanning",
        "note": fallback["note"],
    }


def _request_for(provider: str, key: str, model: str, product: str, industry: str, segments: list[str]) -> tuple[str, dict[str, str], dict[str, Any]]:
    system = (
        "Help a first-time founder turn a product idea into a broad but relevant market-research scope. "
        "Return one JSON object with category_family, suggested_segments (array), comparison_attributes (array), "
        "and search_phrases (array). Suggestions are hypotheses for research, never claims about demand, market size, "
        "or product success. Keep each list concise and avoid invented statistics."
    )
    user = json.dumps({"product": product, "industry": industry, "existing_segments": segments}, ensure_ascii=False)
    if provider == "openrouter":
        return (
            "https://openrouter.ai/api/v1/chat/completions",
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "Scoutwise"},
            {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"},
                "temperature": 0.25,
                "max_tokens": 900,
            },
        )
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='-._')}:generateContent"
    return (
        endpoint,
        {"x-goog-api-key": key, "Content-Type": "application/json"},
        {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.25, "maxOutputTokens": 900},
        },
    )


async def suggest_with_providers(
    brief: dict[str, Any],
    *,
    environ: dict[str, str] | None = None,
    post_json: PostJson | None = None,
) -> dict[str, Any]:
    env = os.environ if environ is None else environ
    product = str(brief.get("product", "")).strip()[:160]
    industry = str(brief.get("industry", "")).strip()[:120]
    segments = [str(item).strip()[:100] for item in brief.get("segments", []) if str(item).strip()][:8]
    fallback = suggest_scope(product, industry, segments)
    request = post_json or _http_post_json
    for provider, key, model in _providers(env):
        try:
            url, headers, payload = _request_for(provider, key, model, product, industry, segments)
            response = await request(url, headers, payload)
            result = _normalise(_parse_json(_json_text(provider, response)), fallback)
            return {**result, "source": "ai", "provider": provider}
        except Exception:
            # Provider errors may include request credentials. Keep them out of logs/responses.
            continue
    return {**fallback, "source": "rule_based_fallback", "provider": None}
