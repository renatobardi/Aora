from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class GenerateResult:
    text: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = field(default=0)


class BaseProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def generate(self, model: str, system: str, user: str, max_tokens: int) -> GenerateResult:
        ...


class AnthropicProvider(BaseProvider):
    def __init__(self, client) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "anthropic"

    def generate(self, model: str, system: str, user: str, max_tokens: int) -> GenerateResult:
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user}],
        )
        usage = response.usage
        return GenerateResult(
            text=response.content[0].text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0),
        )


class GoogleProvider(BaseProvider):
    def __init__(self, client) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "google"

    def generate(self, model: str, system: str, user: str, max_tokens: int) -> GenerateResult:
        from google.genai import types  # noqa: PLC0415

        response = self._client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        meta = response.usage_metadata
        return GenerateResult(
            text=response.text,
            input_tokens=meta.prompt_token_count or 0,
            output_tokens=meta.candidates_token_count or 0,
        )


def create_provider(provider_name: str, api_key: str) -> BaseProvider:
    if provider_name == "google":
        from google import genai  # noqa: PLC0415

        client = genai.Client(api_key=api_key)
        return GoogleProvider(client)
    import anthropic  # noqa: PLC0415

    client = anthropic.Anthropic(api_key=api_key)
    return AnthropicProvider(client)
