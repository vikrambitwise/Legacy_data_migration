"""LLM helper with structured-output + heuristic fallback."""

from __future__ import annotations

import json
from typing import Any

from core.config import get_settings
from core.logging import get_logger
from core.models import new_id
from core.observability import LLMTracer

logger = get_logger("agents.llm")


def make_prompt_id(template_key: str) -> str:
    return f"{template_key}:{new_id('prompt')}"


def get_chat_model():
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    try:
        if settings.llm_provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=settings.llm_model, api_key=api_key, temperature=0)
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": settings.llm_model,
            "api_key": api_key,
            "temperature": 0,
        }
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        return ChatOpenAI(**kwargs)
    except Exception as exc:
        logger.warning("LLM client init failed (%s); using heuristic fallback", exc)
        return None


def invoke_json(
    *,
    tracer: LLMTracer,
    node: str,
    template_key: str,
    prompt: str,
    schema_hint: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return (prompt_id, parsed_json). Heuristic callers should not use this."""
    prompt_id = make_prompt_id(template_key)
    llm = get_chat_model()
    with tracer.span(node, prompt_id=prompt_id, input_payload={"prompt": prompt}) as span:
        if llm is None:
            raise RuntimeError("LLM disabled")
        try:
            from langchain_core.messages import HumanMessage, SystemMessage

            messages = [
                SystemMessage(content="You return only valid JSON. No markdown fences."),
                HumanMessage(content=prompt),
            ]
            config = tracer.langchain_config()
            result = llm.invoke(messages, config=config or None)
            text = result.content if hasattr(result, "content") else str(result)
            parsed = _parse_json(text)
            span["output"] = parsed
            return prompt_id, parsed
        except Exception as exc:
            span["error"] = str(exc)
            logger.warning("LLM invoke failed for %s: %s", template_key, exc)
            raise


def _parse_json(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)
