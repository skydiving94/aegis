"""Gemini LLM client with cost tracking and per-usage-type model resolution."""

from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel

from agent.llm.base_client import (
    AbstractLLMClient,
    LLMResponse,
    ModelUsage,
    UsageStats,
)

# Hardcoded pricing per 1M tokens (input, output) — update as needed
_PRICING: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash": (0.10, 0.40),
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash": (0.15, 0.60),
}

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiClient(AbstractLLMClient):
    """Thin wrapper around google.genai with cost tracking.

    Resolves model per call: explicit model arg > usage_type config > default.
    """

    def __init__(
        self,
        api_key: str,
        default_model: str = _DEFAULT_MODEL,
        model_config: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._default_model = default_model
        self._model_config = model_config or {}
        self._usage: dict[str, ModelUsage] = {}
        self._client: Any = None  # lazily initialized on first send()
        self._genai: Any = None

        try:
            from google import genai  # type: ignore[import-untyped]
            self._genai = genai
        except ImportError:
            pass  # will fail on first send()

    def send(
        self,
        prompt: str,
        system_instruction: str = "",
        model: str | None = None,
        usage_type: str = "default",
        temperature: float = 0.7,
        max_output_tokens: int = 8192,
        thinking_budget: int | None = None,
        response_schema: type[BaseModel] | None = None,
        force_json: bool = False,
    ) -> LLMResponse:
        """Send a prompt to Gemini and track usage."""
        if self._client is None:
            if self._genai is None:
                raise RuntimeError(
                    "google-genai is not installed. Run: pip install google-genai"
                )
            if not self._api_key:
                raise RuntimeError(
                    "GEMINI_API_KEY is not set. Add it to your .env file."
                )
            self._client = self._genai.Client(api_key=self._api_key)

        resolved_model = self._resolve_model(model, usage_type)
        start = time.monotonic()

        # Build contents
        contents = prompt
        sys_instruction = system_instruction if system_instruction else None

        # Build config
        config: dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if thinking_budget is not None:
            config["thinking_config"] = {"thinking_budget": thinking_budget}
        if response_schema is not None:
            config["response_mime_type"] = "application/json"
            config["response_schema"] = response_schema
        elif force_json:
            config["response_mime_type"] = "application/json"
        if sys_instruction:
            config["system_instruction"] = sys_instruction

        response = self._client.models.generate_content(
            model=resolved_model,
            contents=contents,
            config=config,
        )

        latency_ms = int((time.monotonic() - start) * 1000)

        # Extract usage metadata
        input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) or 0
        output_tokens = (
            getattr(response.usage_metadata, "candidates_token_count", 0) or 0
        )
        thinking_tokens = (
            getattr(response.usage_metadata, "thoughts_token_count", 0) or 0
        )

        cost = self._calculate_cost(resolved_model, input_tokens, output_tokens)
        content = response.text or ""

        # Track usage
        if resolved_model not in self._usage:
            self._usage[resolved_model] = ModelUsage()
        stats = self._usage[resolved_model]
        stats.requests += 1
        stats.input_tokens += input_tokens
        stats.output_tokens += output_tokens
        stats.thinking_tokens += thinking_tokens
        stats.cost_usd += cost

        return LLMResponse(
            content=content,
            model=resolved_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    def get_usage_stats(self) -> UsageStats:
        """Return accumulated usage statistics across all models."""
        total = UsageStats(by_model=dict(self._usage))
        for model_stats in self._usage.values():
            total.total_requests += model_stats.requests
            total.total_input_tokens += model_stats.input_tokens
            total.total_output_tokens += model_stats.output_tokens
            total.total_thinking_tokens += model_stats.thinking_tokens
            total.total_cost_usd += model_stats.cost_usd
        return total

    def _resolve_model(self, model: str | None, usage_type: str) -> str:
        """Pick model: explicit > config by usage_type > default."""
        if model is not None:
            return model
        config_key = f"LLM_MODEL_{usage_type.upper()}"
        return self._model_config.get(config_key, self._default_model)

    @staticmethod
    def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculate cost in USD from token counts."""
        pricing = _PRICING.get(model, _PRICING[_DEFAULT_MODEL])
        input_cost = (input_tokens / 1_000_000) * pricing[0]
        output_cost = (output_tokens / 1_000_000) * pricing[1]
        return input_cost + output_cost
