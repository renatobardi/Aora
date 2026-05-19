"""
Tests for main.py CLI behaviour:
  - Help text exposes both API key vars (AI_PROVIDER, ANTHROPIC_API_KEY, GOOGLE_API_KEY)
  - `source add` selects the right key variable based on AI_PROVIDER
"""
import os
import subprocess
import sys

import pytest

_PROJECT = os.path.dirname(os.path.abspath(__file__))
_PYTHON = sys.executable


def _run(*args, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [_PYTHON, "main.py", *args],
        capture_output=True,
        text=True,
        cwd=_PROJECT,
        env=env,
    )


# ── Help text ─────────────────────────────────────────────────────────────────

class TestHelpText:
    """_ENV_ALL and _ENV_SOURCE_ADD must document both providers' API keys."""

    def test_main_help_shows_ai_provider(self):
        result = _run("-h")
        assert "AI_PROVIDER" in result.stdout

    def test_main_help_shows_anthropic_api_key(self):
        result = _run("-h")
        assert "ANTHROPIC_API_KEY" in result.stdout

    def test_main_help_shows_google_api_key(self):
        result = _run("-h")
        assert "GOOGLE_API_KEY" in result.stdout

    def test_source_add_help_shows_ai_provider(self):
        result = _run("source", "add", "-h")
        assert "AI_PROVIDER" in result.stdout

    def test_source_add_help_shows_both_api_keys(self):
        result = _run("source", "add", "-h")
        assert "ANTHROPIC_API_KEY" in result.stdout
        assert "GOOGLE_API_KEY" in result.stdout


# ── source add key selection ───────────────────────────────────────────────────

class TestSourceAddKeySelection:
    """main.py source add must reference the correct API key for each provider.

    load_dotenv(override=False) respects pre-set env vars, so passing an empty
    string forces the missing-key error without touching the .env file.
    """

    def test_google_provider_requires_google_api_key(self):
        result = _run(
            "source", "add", "https://example.com",
            env_extra={"AI_PROVIDER": "google", "GOOGLE_API_KEY": ""},
        )
        assert result.returncode == 1
        assert "GOOGLE_API_KEY" in result.stdout

    def test_anthropic_provider_requires_anthropic_api_key(self):
        result = _run(
            "source", "add", "https://example.com",
            env_extra={"AI_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": ""},
        )
        assert result.returncode == 1
        assert "ANTHROPIC_API_KEY" in result.stdout
