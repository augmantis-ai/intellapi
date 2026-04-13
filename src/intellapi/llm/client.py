"""LLM Client — adapter router with retry logic and JSON validation.

Routes to the correct provider adapter based on config.
Handles structured output validation with one repair retry.
Reports token usage after generation.
"""

from __future__ import annotations

import json
import time

from pydantic import ValidationError

from intellapi.config import IntellapiConfig, Provider
from intellapi.llm.prompts import build_repair_prompt, build_system_prompt, build_user_prompt
from intellapi.llm.schemas import DocumentationDraft
from intellapi.providers.base import BaseProvider, ProviderResponse
from intellapi.providers.anthropic_native import AnthropicNativeProvider
from intellapi.providers.bedrock_native import BedrockNativeProvider
from intellapi.providers.openai_compatible import OpenAICompatibleProvider
from intellapi.scanner.ir import IntermediateRepresentation
from intellapi.utils import console, print_error, print_info, print_success, print_warning


class LLMClient:
    """High-level LLM client that routes to the correct provider."""

    def __init__(self, config: IntellapiConfig):
        self._config = config
        self._provider = self._create_provider()

    def _create_provider(self) -> BaseProvider:
        """Instantiate the correct provider adapter based on config."""
        match self._config.provider:
            case Provider.OPENAI_COMPATIBLE:
                if not self._config.api_key:
                    raise ValueError(
                        "API key required for openai_compatible provider. "
                        "Run 'intellapi init' or set INTELLAPI_API_KEY."
                    )
                return OpenAICompatibleProvider(
                    api_key=self._config.api_key,
                    model=self._config.model or "gpt-4o-mini",
                    base_url=self._config.base_url,
                )

            case Provider.ANTHROPIC:
                if not self._config.api_key:
                    raise ValueError(
                        "API key required for anthropic provider. "
                        "Run 'intellapi init' or set INTELLAPI_API_KEY."
                    )
                return AnthropicNativeProvider(
                    api_key=self._config.api_key,
                    model=self._config.model or "claude-3-5-sonnet-20241022",
                )

            case Provider.BEDROCK:
                return BedrockNativeProvider(
                    model_id=self._config.model or "anthropic.claude-3-haiku-20240307-v1:0",
                    region=self._config.aws_region,
                    profile=self._config.aws_profile,
                )

            case _:
                raise ValueError(
                    f"Unknown provider: {self._config.provider}. "
                    f"Valid options: {', '.join(p.value for p in Provider)}"
                )

    def validate_connection(self) -> bool:
        """Test provider connectivity. Used by `intellapi doctor`."""
        return self._provider.validate_connection()

    @property
    def provider_name(self) -> str:
        return self._provider.provider_name

    def generate_documentation(
        self,
        ir: IntermediateRepresentation,
        max_retries: int = 3,
    ) -> DocumentationDraft:
        """Generate documentation from an IntermediateRepresentation.

        Sends structured code context to the LLM, validates the JSON response,
        and retries once on validation failure (repair prompt).

        Args:
            ir: The intermediate representation from the scanner.
            max_retries: Max retries for transient errors (rate limits, timeouts).

        Returns:
            Validated DocumentationDraft.

        Raises:
            ValueError: If the LLM fails to produce valid output after retries.
        """
        system_prompt = build_system_prompt()
        user_prompt = build_user_prompt(ir, max_output_tokens=self._provider.max_output_tokens)

        # Schema hint (used by providers that support JSON mode)
        schema = DocumentationDraft.model_json_schema()

        # Attempt generation with retries for transient errors
        response = self._call_with_retries(
            system_prompt, user_prompt, schema, max_retries
        )

        # Attempt to parse and validate JSON
        draft = self._parse_response(response.text)
        if draft is not None:
            self._report_usage(response)
            return draft

        # Repair retry — send error back to LLM
        print_warning("LLM output failed validation. Attempting repair...")
        try:
            parse_error = self._get_parse_error(response.text)
            repair_prompt = build_repair_prompt(response.text, parse_error)
            repair_response = self._call_with_retries(
                system_prompt, repair_prompt, schema, max_retries=1
            )
            draft = self._parse_response(repair_response.text)
            if draft is not None:
                total_input = response.input_tokens + repair_response.input_tokens
                total_output = response.output_tokens + repair_response.output_tokens
                combined = ProviderResponse(
                    text=repair_response.text,
                    input_tokens=total_input,
                    output_tokens=total_output,
                    model=repair_response.model,
                    cost_estimate=(
                        (response.cost_estimate or 0) + (repair_response.cost_estimate or 0)
                    ) or None,
                )
                self._report_usage(combined)
                return draft
        except Exception:
            pass

        # Write the raw output to a file for debugging
        last_text = repair_response.text if 'repair_response' in locals() else response.text
        try:
            with open("failed_llm_output.txt", "w", encoding="utf-8") as f:
                f.write(last_text)
        except Exception:
            pass

        error_msg = self._get_parse_error(last_text)
        raise ValueError(
            f"LLM failed to produce valid documentation.\n"
            f"Validation Error: {error_msg}\n"
            f"(Raw text saved to 'failed_llm_output.txt' in your current directory for debugging)"
        )

    def _call_with_retries(
        self,
        system_prompt: str,
        user_prompt: str,
        schema: dict | None,
        max_retries: int,
    ) -> ProviderResponse:
        """Call the provider with exponential backoff retries."""
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                return self._provider.complete(system_prompt, user_prompt, schema)
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print_warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
                    time.sleep(wait)

        raise RuntimeError(f"Provider call failed after {max_retries} attempts: {last_error}")

    def _extract_json(self, text: str) -> str:
        """Robustly extract JSON block from LLM output."""
        cleaned = text.strip()
        import re
        match = re.search(r'(\{.*\})', cleaned, re.DOTALL)
        if match:
            return match.group(1)
        return cleaned

    def _parse_response(self, text: str) -> DocumentationDraft | None:
        """Attempt to parse LLM text as a DocumentationDraft."""
        cleaned = self._extract_json(text)
        
        try:
            data = json.loads(cleaned)
            return DocumentationDraft.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            return None

    def _get_parse_error(self, text: str) -> str:
        """Get a human-readable parse error for the repair prompt."""
        cleaned = self._extract_json(text)

        try:
            data = json.loads(cleaned)
            DocumentationDraft.model_validate(data)
            return "Unknown validation error"
        except json.JSONDecodeError as e:
            return f"Invalid JSON: {e}"
        except ValidationError as e:
            return f"Schema validation failed: {e}"

    def _report_usage(self, response: ProviderResponse) -> None:
        """Print token usage and optional cost estimate."""
        console.print()
        print_info(f"Model: {response.model}")
        print_info(f"Tokens: {response.input_tokens:,} input + {response.output_tokens:,} output")
        if response.cost_estimate is not None:
            print_info(f"Estimated cost: ${response.cost_estimate:.4f}")
        console.print()
