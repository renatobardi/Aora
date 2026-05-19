"""Tests for provider.py and processor.py — both providers and all models."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# ── Stub google.genai before importing provider/processor ─────────────────────
# google-genai may not be installed in the dev environment; stub the module so
# that tests can exercise GoogleProvider logic without a real SDK installed.
_google_stub = MagicMock()
_genai_stub = MagicMock()
_types_stub = MagicMock()
_genai_stub.types = _types_stub
_google_stub.genai = _genai_stub
sys.modules.setdefault("google", _google_stub)
sys.modules.setdefault("google.genai", _genai_stub)
sys.modules.setdefault("google.genai.types", _types_stub)
# ─────────────────────────────────────────────────────────────────────────────

from provider import (  # noqa: E402
    AnthropicProvider,
    BaseProvider,
    GenerateResult,
    GoogleProvider,
    create_provider,
)
import processor as proc  # noqa: E402
from processor import (  # noqa: E402
    _ANTHROPIC_PRICING,
    _GOOGLE_PRICING,
    get_model,
    estimate_cost,
    process_all,
    process_all_async,
    process_all_sync,
    process_item_sync,
)

# ── Constants ─────────────────────────────────────────────────────────────────

ANTHROPIC_MODELS = list(_ANTHROPIC_PRICING.keys())
GOOGLE_MODELS = list(_GOOGLE_PRICING.keys())

SAMPLE_ITEM = {
    "id": "https://example.com/post",
    "title": "GPT-5 released",
    "source_name": "OpenAI",
    "category": "foundation-model",
    "url": "https://example.com/post",
    "published": "2026-05-18",
    "content": "OpenAI releases GPT-5 with 10x performance gains.",
}

VALID_RESPONSE = json.dumps({
    "tldr": "GPT-5 released with 10x perf gains.",
    "por_que_importa": "Sets new SOTA on all benchmarks.",
    "tags": ["foundation-model", "pesquisa"],
})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_anthropic_client(text: str = VALID_RESPONSE, input_tok: int = 100,
                            output_tok: int = 50, cache_tok: int = 30) -> MagicMock:
    client = MagicMock()
    usage = MagicMock()
    usage.input_tokens = input_tok
    usage.output_tokens = output_tok
    usage.cache_read_input_tokens = cache_tok
    content = MagicMock()
    content.text = text
    client.messages.create.return_value = MagicMock(content=[content], usage=usage)
    return client


def _make_google_client(text: str = VALID_RESPONSE, prompt_tok: int = 80,
                         candidates_tok: int = 40) -> MagicMock:
    client = MagicMock()
    meta = MagicMock()
    meta.prompt_token_count = prompt_tok
    meta.candidates_token_count = candidates_tok
    response = MagicMock()
    response.text = text
    response.usage_metadata = meta
    client.models.generate_content.return_value = response
    return client


def _anthropic_provider(text: str = VALID_RESPONSE, **kwargs) -> AnthropicProvider:
    return AnthropicProvider(_make_anthropic_client(text, **kwargs))


def _google_provider(text: str = VALID_RESPONSE, **kwargs) -> GoogleProvider:
    return GoogleProvider(_make_google_client(text, **kwargs))


# ── GenerateResult ────────────────────────────────────────────────────────────

class TestGenerateResult:
    def test_fields(self):
        r = GenerateResult(text="hello", input_tokens=10, output_tokens=5)
        assert r.text == "hello"
        assert r.input_tokens == 10
        assert r.output_tokens == 5

    def test_cached_tokens_defaults_to_zero(self):
        r = GenerateResult(text="x", input_tokens=1, output_tokens=1)
        assert r.cached_tokens == 0

    def test_cached_tokens_explicit(self):
        r = GenerateResult(text="x", input_tokens=1, output_tokens=1, cached_tokens=99)
        assert r.cached_tokens == 99


# ── BaseProvider interface ────────────────────────────────────────────────────

class TestBaseProvider:
    def test_anthropic_implements_base(self):
        assert isinstance(_anthropic_provider(), BaseProvider)

    def test_google_implements_base(self):
        assert isinstance(_google_provider(), BaseProvider)

    def test_anthropic_name(self):
        assert _anthropic_provider().name == "anthropic"

    def test_google_name(self):
        assert _google_provider().name == "google"


# ── AnthropicProvider ─────────────────────────────────────────────────────────

class TestAnthropicProvider:
    def test_generate_returns_result(self):
        provider = _anthropic_provider()
        result = provider.generate("claude-haiku-4-5-20251001", "sys", "user", 300)
        assert isinstance(result, GenerateResult)

    def test_generate_text(self):
        provider = _anthropic_provider(text="hello")
        result = provider.generate("model", "sys", "user", 100)
        assert result.text == "hello"

    def test_generate_token_counts(self):
        provider = _anthropic_provider(input_tok=111, output_tok=22, cache_tok=33)
        result = provider.generate("model", "sys", "user", 100)
        assert result.input_tokens == 111
        assert result.output_tokens == 22
        assert result.cached_tokens == 33

    def test_calls_messages_create(self):
        client = _make_anthropic_client()
        provider = AnthropicProvider(client)
        provider.generate("claude-haiku-4-5-20251001", "sys", "user msg", 300)
        client.messages.create.assert_called_once()

    def test_passes_model(self):
        client = _make_anthropic_client()
        provider = AnthropicProvider(client)
        provider.generate("claude-sonnet-4-6", "sys", "user", 300)
        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-6"

    def test_passes_max_tokens(self):
        client = _make_anthropic_client()
        provider = AnthropicProvider(client)
        provider.generate("model", "sys", "user", 512)
        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["max_tokens"] == 512

    def test_system_has_cache_control(self):
        client = _make_anthropic_client()
        provider = AnthropicProvider(client)
        provider.generate("model", "my system", "user", 100)
        call_kwargs = client.messages.create.call_args.kwargs
        system = call_kwargs["system"]
        assert isinstance(system, list)
        assert system[0]["cache_control"] == {"type": "ephemeral"}
        assert system[0]["text"] == "my system"

    def test_user_message_content(self):
        client = _make_anthropic_client()
        provider = AnthropicProvider(client)
        provider.generate("model", "sys", "my user message", 100)
        call_kwargs = client.messages.create.call_args.kwargs
        assert call_kwargs["messages"][0]["content"] == "my user message"

    def test_cached_tokens_fallback_when_missing(self):
        client = MagicMock()
        usage = MagicMock(spec=["input_tokens", "output_tokens"])
        usage.input_tokens = 10
        usage.output_tokens = 5
        content = MagicMock()
        content.text = VALID_RESPONSE
        client.messages.create.return_value = MagicMock(content=[content], usage=usage)
        provider = AnthropicProvider(client)
        result = provider.generate("model", "sys", "user", 100)
        assert result.cached_tokens == 0


# ── GoogleProvider ────────────────────────────────────────────────────────────

class TestGoogleProvider:
    def test_generate_returns_result(self):
        provider = _google_provider()
        result = provider.generate("gemini-2.5-flash", "sys", "user", 300)
        assert isinstance(result, GenerateResult)

    def test_generate_text(self):
        provider = GoogleProvider(_make_google_client(text="gemini response"))
        result = provider.generate("gemini-2.5-flash", "sys", "user", 100)
        assert result.text == "gemini response"

    def test_generate_token_counts(self):
        provider = GoogleProvider(_make_google_client(prompt_tok=70, candidates_tok=25))
        result = provider.generate("gemini-2.5-flash", "sys", "user", 100)
        assert result.input_tokens == 70
        assert result.output_tokens == 25
        assert result.cached_tokens == 0

    def test_calls_generate_content(self):
        client = _make_google_client()
        provider = GoogleProvider(client)
        provider.generate("gemini-2.5-pro", "sys", "user", 300)
        client.models.generate_content.assert_called_once()

    def test_passes_model(self):
        client = _make_google_client()
        provider = GoogleProvider(client)
        provider.generate("gemini-2.5-pro", "sys", "user", 300)
        call_kwargs = client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-2.5-pro"

    def test_passes_user_as_contents(self):
        client = _make_google_client()
        provider = GoogleProvider(client)
        provider.generate("model", "sys", "my user content", 300)
        call_kwargs = client.models.generate_content.call_args.kwargs
        assert call_kwargs["contents"] == "my user content"

    def test_null_token_counts_become_zero(self):
        client = _make_google_client()
        client.models.generate_content.return_value.usage_metadata.prompt_token_count = None
        client.models.generate_content.return_value.usage_metadata.candidates_token_count = None
        provider = GoogleProvider(client)
        result = provider.generate("model", "sys", "user", 100)
        assert result.input_tokens == 0
        assert result.output_tokens == 0


# ── create_provider factory ───────────────────────────────────────────────────

class TestCreateProvider:
    def test_anthropic_returns_anthropic_provider(self):
        with patch("anthropic.Anthropic"):
            provider = create_provider("anthropic", "sk-ant-fake")
        assert isinstance(provider, AnthropicProvider)

    def test_google_returns_google_provider(self):
        provider = create_provider("google", "AIza-fake")
        assert isinstance(provider, GoogleProvider)

    def test_unknown_defaults_to_anthropic(self):
        with patch("anthropic.Anthropic"):
            provider = create_provider("unknown_provider", "key")
        assert isinstance(provider, AnthropicProvider)

    def test_anthropic_uses_api_key(self):
        with patch("anthropic.Anthropic") as mock_cls:
            create_provider("anthropic", "sk-ant-test123")
        mock_cls.assert_called_once_with(api_key="sk-ant-test123")

    def test_google_uses_api_key(self):
        create_provider("google", "AIza-test456")
        _genai_stub.Client.assert_called_with(api_key="AIza-test456")


# ── get_model ─────────────────────────────────────────────────────────────────

class TestGetModel:
    def test_anthropic_default(self):
        provider = MagicMock()
        provider.name = "anthropic"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_MODEL", None)
            assert get_model(provider) == "claude-haiku-4-5-20251001"

    def test_google_default(self):
        provider = MagicMock()
        provider.name = "google"
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_MODEL", None)
            assert get_model(provider) == "gemini-2.5-flash-lite"

    @pytest.mark.parametrize("model", ANTHROPIC_MODELS)
    def test_anthropic_env_override(self, model):
        provider = MagicMock()
        provider.name = "anthropic"
        with patch.dict(os.environ, {"ANTHROPIC_MODEL": model}):
            assert get_model(provider) == model

    @pytest.mark.parametrize("model", GOOGLE_MODELS)
    def test_google_env_override(self, model):
        provider = MagicMock()
        provider.name = "google"
        with patch.dict(os.environ, {"GOOGLE_MODEL": model}):
            assert get_model(provider) == model


# ── estimate_cost ─────────────────────────────────────────────────────────────

class TestEstimateCost:
    @pytest.mark.parametrize("model,price_in,price_out", [
        ("claude-haiku-4-5-20251001", 1.00, 5.00),
        ("claude-3-5-haiku-latest",   1.00, 5.00),
        ("claude-3-7-sonnet-latest",  3.00, 15.00),
        ("claude-sonnet-4-6",         3.00, 15.00),
        ("claude-opus-4-7",           5.00, 25.00),
    ])
    def test_anthropic_sync_pricing(self, model, price_in, price_out):
        cost = estimate_cost(1_000_000, 1_000_000, 0, is_async=False,
                             provider_name="anthropic", model=model)
        assert abs(cost - (price_in + price_out)) < 0.001

    @pytest.mark.parametrize("model,price_in,price_out", [
        ("claude-haiku-4-5-20251001", 1.00, 5.00),
        ("claude-opus-4-7",           5.00, 25.00),
    ])
    def test_anthropic_async_50pct_discount(self, model, price_in, price_out):
        sync_cost = estimate_cost(1_000_000, 1_000_000, 0, is_async=False,
                                  provider_name="anthropic", model=model)
        async_cost = estimate_cost(1_000_000, 1_000_000, 0, is_async=True,
                                   provider_name="anthropic", model=model)
        assert abs(async_cost - sync_cost * 0.5) < 0.001

    def test_anthropic_cache_read_10pct_of_input(self):
        # For Haiku ($1.00/M input), cache read = $0.10/M
        cost = estimate_cost(0, 0, 1_000_000, is_async=False,
                             provider_name="anthropic", model="claude-haiku-4-5-20251001")
        assert abs(cost - 0.10) < 0.001

    def test_anthropic_cache_read_not_discounted_by_async(self):
        cost_sync = estimate_cost(0, 0, 1_000_000, is_async=False,
                                  provider_name="anthropic", model="claude-haiku-4-5-20251001")
        cost_async = estimate_cost(0, 0, 1_000_000, is_async=True,
                                   provider_name="anthropic", model="claude-haiku-4-5-20251001")
        assert abs(cost_sync - cost_async) < 0.001

    @pytest.mark.parametrize("model,price_in,price_out", [
        ("gemini-2.5-flash-lite", 0.10,  0.40),
        ("gemini-2.5-flash",      0.30,  2.50),
        ("gemini-2.5-pro",        1.25, 10.00),
        ("gemini-3.1-flash-lite", 0.25,  1.50),
        ("gemini-3-flash-preview",0.50,  3.00),
    ])
    def test_google_pricing(self, model, price_in, price_out):
        cost = estimate_cost(1_000_000, 1_000_000, 0, provider_name="google", model=model)
        assert abs(cost - (price_in + price_out)) < 0.001

    def test_google_ignores_cached_tokens(self):
        cost_no_cache = estimate_cost(1_000_000, 0, 0, provider_name="google",
                                      model="gemini-2.5-flash")
        cost_with_cache = estimate_cost(1_000_000, 0, 500_000, provider_name="google",
                                        model="gemini-2.5-flash")
        assert cost_no_cache == cost_with_cache

    def test_google_ignores_is_async_flag(self):
        cost_sync = estimate_cost(1_000_000, 1_000_000, 0, is_async=False,
                                  provider_name="google", model="gemini-2.5-flash")
        cost_async = estimate_cost(1_000_000, 1_000_000, 0, is_async=True,
                                   provider_name="google", model="gemini-2.5-flash")
        assert cost_sync == cost_async

    def test_unknown_anthropic_model_uses_fallback(self):
        cost = estimate_cost(1_000_000, 1_000_000, 0, provider_name="anthropic",
                             model="claude-unknown-9000")
        assert cost > 0

    def test_unknown_google_model_uses_fallback(self):
        cost = estimate_cost(1_000_000, 1_000_000, 0, provider_name="google",
                             model="gemini-unknown-42")
        assert cost > 0

    def test_zero_tokens_zero_cost(self):
        for provider_name in ("anthropic", "google"):
            cost = estimate_cost(0, 0, 0, provider_name=provider_name,
                                 model="claude-haiku-4-5-20251001")
            assert cost == 0.0


# ── process_item_sync ─────────────────────────────────────────────────────────

class TestProcessItemSync:
    def test_anthropic_enriches_item(self):
        provider = _anthropic_provider()
        result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        assert result["tldr"] == "GPT-5 released with 10x perf gains."
        assert result["por_que_importa"] == "Sets new SOTA on all benchmarks."
        assert "foundation-model" in result["tags"]

    def test_google_enriches_item(self):
        provider = _google_provider()
        result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        assert result["tldr"] == "GPT-5 released with 10x perf gains."

    def test_anthropic_token_counts(self):
        provider = _anthropic_provider(input_tok=200, output_tok=80, cache_tok=50)
        result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        assert result["tokens_input"] == 200
        assert result["tokens_output"] == 80
        assert result["tokens_cache_read"] == 50

    def test_google_token_counts(self):
        provider = GoogleProvider(_make_google_client(prompt_tok=150, candidates_tok=60))
        result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        assert result["tokens_input"] == 150
        assert result["tokens_output"] == 60
        assert result["tokens_cache_read"] == 0

    def test_invalid_tags_filtered(self):
        bad_resp = json.dumps({
            "tldr": "T", "por_que_importa": "P",
            "tags": ["foundation-model", "invalid-tag", "pesquisa"]
        })
        provider = _anthropic_provider(text=bad_resp)
        result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        assert "invalid-tag" not in result["tags"]
        assert "foundation-model" in result["tags"]

    def test_fallback_on_provider_exception(self):
        provider = MagicMock()
        provider.name = "anthropic"
        provider.generate.side_effect = Exception("API error")
        with patch("processor.get_model", return_value="claude-haiku-4-5-20251001"):
            result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        assert result["tokens_input"] == 0
        assert result["tldr"] != ""  # fallback uses content/title

    def test_fallback_on_invalid_json(self):
        provider = _anthropic_provider(text="not valid json")
        result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        assert result["tokens_input"] == 0

    def test_original_fields_preserved(self):
        provider = _anthropic_provider()
        result = process_item_sync(SAMPLE_ITEM.copy(), provider)
        for key in ("id", "url", "published", "source_name", "category"):
            assert result[key] == SAMPLE_ITEM[key]

    @pytest.mark.parametrize("model", ANTHROPIC_MODELS)
    def test_anthropic_all_models_call_generate(self, model):
        provider = MagicMock()
        provider.name = "anthropic"
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=10, output_tokens=5
        )
        with patch.dict(os.environ, {"ANTHROPIC_MODEL": model}):
            process_item_sync(SAMPLE_ITEM.copy(), provider)
        provider.generate.assert_called_once()
        call_args = provider.generate.call_args
        assert call_args.kwargs["model"] == model or call_args.args[0] == model

    @pytest.mark.parametrize("model", GOOGLE_MODELS)
    def test_google_all_models_call_generate(self, model):
        provider = MagicMock()
        provider.name = "google"
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=10, output_tokens=5
        )
        with patch.dict(os.environ, {"GOOGLE_MODEL": model}):
            process_item_sync(SAMPLE_ITEM.copy(), provider)
        provider.generate.assert_called_once()


# ── process_all_sync ──────────────────────────────────────────────────────────

class TestProcessAllSync:
    def _make_provider(self) -> MagicMock:
        provider = MagicMock()
        provider.name = "anthropic"
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=10, output_tokens=5, cached_tokens=2
        )
        return provider

    def test_returns_correct_count(self):
        items = [SAMPLE_ITEM.copy() for _ in range(3)]
        provider = self._make_provider()
        enriched, inp, out, cache = process_all_sync(items, provider)
        assert len(enriched) == 3

    def test_aggregates_tokens(self):
        items = [SAMPLE_ITEM.copy() for _ in range(3)]
        provider = self._make_provider()
        _, inp, out, cache = process_all_sync(items, provider)
        assert inp == 30
        assert out == 15
        assert cache == 6

    def test_empty_list(self):
        provider = self._make_provider()
        enriched, inp, out, cache = process_all_sync([], provider)
        assert enriched == []
        assert inp == out == cache == 0

    def test_works_with_google_provider(self):
        items = [SAMPLE_ITEM.copy() for _ in range(2)]
        provider = MagicMock()
        provider.name = "google"
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=80, output_tokens=40
        )
        enriched, inp, out, cache = process_all_sync(items, provider)
        assert len(enriched) == 2
        assert inp == 160
        assert cache == 0


# ── process_all_async ─────────────────────────────────────────────────────────

class TestProcessAllAsync:
    def _make_batch_client(self, n_items: int) -> MagicMock:
        client = MagicMock()
        batch = MagicMock()
        batch.id = "batch_test_123"
        client.messages.batches.create.return_value = batch

        status = MagicMock()
        status.processing_status = "ended"
        client.messages.batches.retrieve.return_value = status

        results = []
        for i in range(n_items):
            res = MagicMock()
            res.custom_id = str(i)
            res.result.type = "succeeded"
            res.result.message.content = [MagicMock(text=VALID_RESPONSE)]
            usage = MagicMock()
            usage.input_tokens = 10
            usage.output_tokens = 5
            res.result.message.usage = usage
            results.append(res)

        client.messages.batches.results.return_value = iter(results)
        return client

    def test_anthropic_uses_batch_api(self):
        items = [SAMPLE_ITEM.copy() for _ in range(2)]
        client = self._make_batch_client(2)
        provider = AnthropicProvider(client)
        enriched, _, _, _ = process_all_async(items, provider)
        client.messages.batches.create.assert_called_once()
        assert len(enriched) == 2

    def test_google_falls_back_to_sync(self, capsys):
        items = [SAMPLE_ITEM.copy() for _ in range(2)]
        provider = MagicMock(spec=["name", "generate", "supports_batch"])
        provider.name = "google"
        provider.supports_batch = False
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=50, output_tokens=20
        )
        enriched, _, _, _ = process_all_async(items, provider)
        out = capsys.readouterr().out
        assert "Batch API não disponível" in out or len(enriched) == 2

    def test_google_fallback_enriches_all_items(self):
        items = [SAMPLE_ITEM.copy() for _ in range(3)]
        provider = MagicMock(spec=["name", "generate", "supports_batch"])
        provider.name = "google"
        provider.supports_batch = False
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=50, output_tokens=20
        )
        enriched, _, _, _ = process_all_async(items, provider)
        assert len(enriched) == 3

    def test_anthropic_batch_token_aggregation(self):
        items = [SAMPLE_ITEM.copy() for _ in range(3)]
        client = self._make_batch_client(3)
        provider = AnthropicProvider(client)
        _, inp, out, _ = process_all_async(items, provider)
        assert inp == 30
        assert out == 15

    def test_anthropic_empty_list(self):
        provider = AnthropicProvider(MagicMock())
        enriched, inp, out, cache = process_all_async([], provider)
        assert enriched == [] and inp == out == cache == 0


# ── process_all dispatcher ────────────────────────────────────────────────────

class TestProcessAll:
    def _sync_provider(self) -> MagicMock:
        provider = MagicMock()
        provider.name = "anthropic"
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=10, output_tokens=5
        )
        return provider

    def test_sync_mode_returns_is_async_false(self):
        items = [SAMPLE_ITEM.copy()]
        provider = self._sync_provider()
        with patch.dict(os.environ, {"PROCESS_MODE": "sync"}):
            _, _, _, _, is_async = process_all(items, provider)
        assert is_async is False

    def test_async_mode_anthropic_returns_is_async_true(self):
        items = [SAMPLE_ITEM.copy()]
        client = MagicMock()
        batch = MagicMock()
        batch.id = "b1"
        client.messages.batches.create.return_value = batch
        status = MagicMock()
        status.processing_status = "ended"
        client.messages.batches.retrieve.return_value = status
        res = MagicMock()
        res.custom_id = "0"
        res.result.type = "succeeded"
        res.result.message.content = [MagicMock(text=VALID_RESPONSE)]
        res.result.message.usage = MagicMock(input_tokens=10, output_tokens=5)
        client.messages.batches.results.return_value = iter([res])
        provider = AnthropicProvider(client)
        with patch.dict(os.environ, {"PROCESS_MODE": "async"}):
            _, _, _, _, is_async = process_all(items, provider)
        assert is_async is True

    def test_async_mode_google_returns_is_async_false(self):
        items = [SAMPLE_ITEM.copy()]
        provider = MagicMock(spec=["name", "generate", "supports_batch"])
        provider.name = "google"
        provider.supports_batch = False
        provider.generate.return_value = GenerateResult(
            text=VALID_RESPONSE, input_tokens=10, output_tokens=5
        )
        with patch.dict(os.environ, {"PROCESS_MODE": "async"}):
            _, _, _, _, is_async = process_all(items, provider)
        assert is_async is False

    def test_default_mode_is_sync(self):
        items = [SAMPLE_ITEM.copy()]
        provider = self._sync_provider()
        env = {k: v for k, v in os.environ.items() if k != "PROCESS_MODE"}
        with patch.dict(os.environ, env, clear=True):
            _, _, _, _, is_async = process_all(items, provider)
        assert is_async is False
