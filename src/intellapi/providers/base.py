"""Abstract base provider adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel


class ProviderResponse(BaseModel):
    """Standardized response from any LLM provider."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    cost_estimate: float | None = None  # Best-effort, often unavailable


class BaseProvider(ABC):
    """Abstract interface that all provider adapters implement."""

    @abstractmethod
    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
    ) -> ProviderResponse:
        """Send a prompt to the LLM and return a structured response.

        Args:
            system_prompt: System-level instructions for the LLM.
            user_prompt: The user message containing code context.
            response_schema: Optional JSON schema hint. Not all providers
                support native structured output — callers must validate.

        Returns:
            ProviderResponse with the LLM's text output and token usage.
        """
        ...

    @abstractmethod
    def validate_connection(self) -> bool:
        """Test connectivity to the provider. Used by `intellapi doctor`.

        Returns True if the provider is reachable and credentials are valid.
        """
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name for display."""
        ...

    @property
    @abstractmethod
    def max_output_tokens(self) -> int:
        """The maximum number of output tokens this provider/model supports."""
        ...
