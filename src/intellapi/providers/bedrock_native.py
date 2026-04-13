"""AWS Bedrock native provider adapter.

Uses boto3's Converse API for a unified interface across Bedrock models.
Authentication relies entirely on the standard AWS credential chain —
no custom key prompting, no keyring storage.

Verified models (v1): Claude 3 Haiku, Claude 3.5 Sonnet, Claude 3 Opus.
Unverified models emit a warning but are not blocked.
"""

from __future__ import annotations

import boto3
from botocore.exceptions import ClientError, NoCredentialsError

from intellapi.providers.base import BaseProvider, ProviderResponse
from intellapi.utils import print_warning

# Models we have explicitly verified against the Converse API
VERIFIED_MODELS: dict[str, str] = {
    "anthropic.claude-3-haiku-20240307-v1:0": "Claude 3 Haiku",
    "anthropic.claude-3-5-sonnet-20241022-v2:0": "Claude 3.5 Sonnet v2",
    "anthropic.claude-3-opus-20240229-v1:0": "Claude 3 Opus",
    "anthropic.claude-3-5-haiku-20241022-v1:0": "Claude 3.5 Haiku",
    "anthropic.claude-haiku-4-5-20251001-v1:0": "Claude Haiku 4.5",
}


class BedrockNativeProvider(BaseProvider):
    """Adapter for AWS Bedrock using the Converse API."""

    def __init__(
        self,
        model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
        region: str = "us-east-1",
        profile: str | None = None,
        max_tokens: int | None = None,
    ):
        self._model_id = model_id
        self._region = region
        if max_tokens is None:
            # AWS Bedrock enforces strict 8192 max limits on Anthropic models currently, even 4.5
            self._max_tokens = 8192
        else:
            self._max_tokens = max_tokens

        # Build boto3 session — uses standard AWS credential chain
        session_kwargs: dict = {"region_name": region}
        if profile:
            session_kwargs["profile_name"] = profile

        session = boto3.Session(**session_kwargs)
        self._client = session.client("bedrock-runtime")

        # Warn if using an unverified model
        is_verified = any(key in model_id for key in VERIFIED_MODELS)
        if not is_verified:
            print_warning(
                f"Model '{model_id}' is not verified for Intellapi v1. "
                f"Verified models: {', '.join(VERIFIED_MODELS.values())}. "
                f"Proceeding anyway -- results may vary."
            )

    @property
    def provider_name(self) -> str:
        model_name = next((name for key, name in VERIFIED_MODELS.items() if key in self._model_id), self._model_id)
        return f"AWS Bedrock ({model_name})"

    @property
    def max_output_tokens(self) -> int:
        return self._max_tokens

    def complete(
        self,
        system_prompt: str,
        user_prompt: str,
        response_schema: dict | None = None,
    ) -> ProviderResponse:
        # Structured output: achieved via prompt instruction.
        # The Converse API does not have a native JSON mode -- we validate locally.
        converse_kwargs: dict = {
            "modelId": self._model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [{"text": user_prompt}],
                },
            ],
            "system": [{"text": system_prompt}],
            "inferenceConfig": {
                "maxTokens": self._max_tokens,
                "temperature": 0.2,
            },
        }

        response = self._client.converse(**converse_kwargs)

        # Extract response text
        output_message = response["output"]["message"]
        text = ""
        for block in output_message["content"]:
            if "text" in block:
                text += block["text"]

        # Extract usage
        usage = response.get("usage", {})
        input_tokens = usage.get("inputTokens", 0)
        output_tokens = usage.get("outputTokens", 0)

        return ProviderResponse(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model=self._model_id,
            cost_estimate=None,  # Bedrock pricing varies by account; best-effort omitted
        )

    def validate_connection(self) -> bool:
        """Test connectivity with a minimal Converse call."""
        try:
            response = self._client.converse(
                modelId=self._model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": "ping"}],
                    },
                ],
                inferenceConfig={"maxTokens": 10},
            )
            return True
        except NoCredentialsError:
            print_warning(
                "No AWS credentials found. Configure via:\n"
                "  • AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars\n"
                "  • ~/.aws/credentials file\n"
                "  • aws configure sso\n"
                "  • IAM instance role"
            )
            return False
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "AccessDeniedException":
                print_warning(
                    f"Access denied to model '{self._model_id}'. "
                    f"Ensure you have requested model access in the Bedrock console "
                    f"for region '{self._region}'."
                )
            else:
                print_warning(f"Bedrock error: {e}")
            return False
        except Exception as e:
            print_warning(f"Bedrock connectivity check failed: {e}")
            return False
