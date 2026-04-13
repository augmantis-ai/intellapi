"""OpenAI-compatible provider adapter.

Covers: OpenAI, OpenRouter, Ollama, vLLM, LM Studio, Kimi,
and any endpoint implementing the OpenAI Chat Completions API.
The `base_url` field distinguishes sub-variants.
"""

from __future__ import annotations

import httpx

from intellapi.providers.base import BaseProvider, ProviderResponse
from intellapi.utils import print_warning

# Known pricing per 1M tokens (input, output). Best-effort, may be outdated.
_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4-turbo": (10.00, 30.00),
}

# Models known to support response_format: json_object
_JSON_MODE_MODELS: set[str] = {
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4-turbo-preview",
}


class OpenAICompatibleProvider(BaseProvider):
    """Adapter for any OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout: float = 120.0,
    ):
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self._timeout),
        )

    @property
    def provider_name(self) -> str:
        if "openrouter" in self._base_url:
            return "OpenRouter"
        if "localhost" in self._base_url or "127.0.0.1" in self._base_url:
            return "Local (OpenAI-compatible)"
        if "api.openai.com" in self._base_url:
            return "OpenAI"
        return f"OpenAI-compatible ({self._base_url})"

    @property
    def max_output_tokens(self) -> int:
        _model = self._model.lower()
        if "gpt-5" in _model or "o3" in _model or "o1" in _model:
            return 100000
        # Modern OpenAI models (e.g., gpt-4o) support 16,384 output tokens
        return 16384

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
    ) -> ProviderResponse:
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }

        # Use native JSON mode if the model supports it
        if response_schema and self._supports_json_mode():
            payload["response_format"] = {"type": "json_object"}

        response = self._client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)

        return ProviderResponse(
            text=choice["message"]["content"],
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=data.get("model", self._model),
            cost_estimate=self._estimate_cost(input_tokens, output_tokens),
        )

    def validate_connection(self) -> bool:
        """Test connectivity by listing models."""
        try:
            response = self._client.get("/models")
            return response.status_code == 200
        except (httpx.HTTPError, Exception):
            return False

    def _supports_json_mode(self) -> bool:
        """Check if the current model is known to support JSON mode."""
        # For non-OpenAI endpoints, we can't guarantee support
        if "api.openai.com" not in self._base_url:
            return False
        return any(self._model.startswith(m) for m in _JSON_MODE_MODELS)

    def _estimate_cost(self, input_tokens: int, output_tokens: int) -> float | None:
        """Best-effort cost estimate. Returns None for unknown models."""
        for model_prefix, (in_price, out_price) in _PRICING.items():
            if self._model.startswith(model_prefix):
                return (input_tokens * in_price + output_tokens * out_price) / 1_000_000
        return None

    def __del__(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass
