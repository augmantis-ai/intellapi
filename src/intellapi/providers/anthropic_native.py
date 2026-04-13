"""Anthropic native provider adapter.

Uses the official `anthropic` Python SDK for Claude models via Anthropic's API.
Structured output is achieved via prompt instruction + local validation,
not assumed-stable native features.
"""

from __future__ import annotations

import anthropic

from intellapi.providers.base import BaseProvider, ProviderResponse

# Known pricing per 1M tokens (input, output)
_PRICING: dict[str, tuple[float, float]] = {
    "claude-3-5-sonnet": (3.00, 15.00),
    "claude-3-haiku": (0.25, 1.25),
    "claude-3-opus": (15.00, 75.00),
    "claude-3-5-haiku": (1.00, 5.00),
}


class AnthropicNativeProvider(BaseProvider):
    """Adapter for Claude models via Anthropic's Messages API."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int | None = None,
    ):
        self._api_key = api_key
        self._model = model
        if max_tokens is None:
            self._max_tokens = 64000 if "4.5" in model or "4-5" in model else 8192
        else:
            self._max_tokens = max_tokens
        self._client = anthropic.Anthropic(api_key=self._api_key)

    @property
    def provider_name(self) -> str:
        return "Anthropic"

    @property
    def max_output_tokens(self) -> int:
        return self._max_tokens

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
    ) -> ProviderResponse:
        # Structured output: instruct via prompt, validate locally.
        # We do NOT rely on output_config / structured outputs beta for v1 stability.
        message = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            temperature=0.2,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )

        text = ""
        for block in message.content:
            if block.type == "text":
                text += block.text

        input_tokens = message.usage.input_tokens
        output_tokens = message.usage.output_tokens

        return ProviderResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model,
            cost_estimate=self._estimate_cost(input_tokens, output_tokens),
        )

    def validate_connection(self) -> bool:
        """Test connectivity with a minimal prompt."""
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """Best-effort cost estimate based on known pricing."""
        for model_prefix, (in_price, out_price) in _PRICING.items():
            if self._model.startswith(model_prefix):
                return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
        return None
