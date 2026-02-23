"""Abstract base for LLM clients."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field


class ModelUsage(BaseModel):
    """Per-model usage statistics."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cost_usd: float = 0.0


class UsageStats(BaseModel):
    """Aggregate LLM usage statistics."""

    total_requests: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_thinking_tokens: int = 0
    total_cost_usd: float = 0.0
    by_model: dict[str, ModelUsage] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    """Response from an LLM call."""

    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    thinking_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class AbstractLLMClient(ABC):
    """ABC for LLM client implementations."""

    @abstractmethod
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
        """Send a prompt to the LLM.

        Args:
            prompt: The user prompt text.
            system_instruction: Optional system-level instruction.
            model: Explicit model override. If None, resolved via usage_type.
            usage_type: Semantic key (e.g. "intent", "code_generation") for
                        model resolution from config.
            temperature: Sampling temperature.
            max_output_tokens: Maximum output length.
            thinking_budget: Token budget for extended thinking (Gemini).
            response_schema: Pydantic model for structured output enforcement.

        Returns:
            LLMResponse with content and usage metadata.
        """
        ...

    @abstractmethod
    def get_usage_stats(self) -> UsageStats:
        """Return accumulated usage statistics."""
        ...
