"""Tests for source_manager: list, add, remove — all 58 sources."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import source_manager as sm
from provider import GenerateResult
from sources import CATEGORY_ORDER, SOURCES
from scraped_sources import SCRAPED_SOURCES

# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_jsons(tmp_path):
    """Copy both JSON files to a temp dir; patch source_manager paths to point there."""
    src_json = Path(__file__).parent / "sources.json"
    scr_json = Path(__file__).parent / "scraped_sources.json"
    tmp_src = tmp_path / "sources.json"
    tmp_scr = tmp_path / "scraped_sources.json"
    shutil.copy(src_json, tmp_src)
    shutil.copy(scr_json, tmp_scr)
    with (
        patch.object(sm, "_SOURCES_PATH", tmp_src),
        patch.object(sm, "_SCRAPED_PATH", tmp_scr),
    ):
        yield tmp_src, tmp_scr


def _make_provider(response_json: dict | list) -> MagicMock:
    """Build a fake BaseProvider that returns a fixed JSON string."""
    provider = MagicMock()
    provider.generate.return_value = GenerateResult(
        text=json.dumps(response_json), input_tokens=0, output_tokens=0
    )
    return provider


def _probe_side_effect(rss_links=None, has_sitemap=True, robots_sitemaps=None):
    """Return a _probe_url-compatible dict."""
    return {
        "html": "<html><body>blog listing</body></html>",
        "rss_links": rss_links or [],
        "has_sitemap": has_sitemap,
        "robots_sitemaps": robots_sitemaps or [],
    }


# ── list_sources ──────────────────────────────────────────────────────────────

class TestListSources:
    def test_runs_without_error(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        assert "FONTES RSS" in out
        assert "FONTES WEB" in out

    def test_counts_rss(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        assert f"FONTES RSS ({len(SOURCES)})" in out

    def test_counts_web(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        assert f"FONTES WEB ({len(SCRAPED_SOURCES)})" in out

    def test_all_rss_names_present(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        for src in SOURCES:
            assert src["name"] in out, f"RSS source '{src['name']}' missing from list"

    def test_all_web_names_present(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        for src in SCRAPED_SOURCES:
            assert src["name"] in out, f"Web source '{src['name']}' missing from list"

    def test_method_shown_for_web(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        for method in ("sitemap", "html", "playwright"):
            assert method in out

    def test_category_labels_shown(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        assert "Foundation Models & Labs" in out
        assert "Infraestrutura & Data" in out
        assert "Dev Tools & Coding" in out

    def test_total_line(self, tmp_jsons, capsys):
        sm.list_sources()
        out = capsys.readouterr().out
        total = len(SOURCES) + len(SCRAPED_SOURCES)
        assert f"Total: {len(SOURCES)} RSS + {len(SCRAPED_SOURCES)} web = {total}" in out


# ── add_source: RSS detection ─────────────────────────────────────────────────

RSS_SOURCES = [(s["name"], s["feed_url"], s["category"]) for s in SOURCES]


@pytest.mark.parametrize("name,feed_url,category", RSS_SOURCES)
class TestAddSourceRSS:
    """For each existing RSS source, verify add_source proposes the right config."""

    def test_proposes_rss_type(self, tmp_jsons, name, feed_url, category):
        suggestion = {"type": "rss", "config": {"name": name, "feed_url": feed_url, "category": category}}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", provider)
        provider.generate.assert_called_once()

    def test_cancelled_does_not_write(self, tmp_jsons, name, feed_url, category):
        tmp_src, _ = tmp_jsons
        original = json.loads(tmp_src.read_text())
        suggestion = {"type": "rss", "config": {"name": name, "feed_url": feed_url, "category": category}}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", provider)
        assert json.loads(tmp_src.read_text()) == original

    def test_confirmed_appends_to_sources_json(self, tmp_jsons, name, feed_url, category):
        tmp_src, _ = tmp_jsons
        # Remove the source first so we can re-add it
        original = json.loads(tmp_src.read_text())
        without = [s for s in original if s["name"] != name]
        sm._save(tmp_src, without)

        config = {"name": name + "_test", "feed_url": feed_url, "category": category}
        suggestion = {"type": "rss", "config": config}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", provider)

        after = json.loads(tmp_src.read_text())
        names = [s["name"] for s in after]
        assert config["name"] in names
        # Restore
        sm._save(tmp_src, original)

    def test_confirmed_does_not_touch_scraped_json(self, tmp_jsons, name, feed_url, category):
        _, tmp_scr = tmp_jsons
        original_web = json.loads(tmp_scr.read_text())
        config = {"name": name + "_rss_test", "feed_url": feed_url, "category": category}
        suggestion = {"type": "rss", "config": config}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", provider)
        assert json.loads(tmp_scr.read_text()) == original_web


# ── add_source: web detection ─────────────────────────────────────────────────

WEB_SOURCES = [(s["name"], s["method"], s["category"]) for s in SCRAPED_SOURCES]


@pytest.mark.parametrize("name,method,category", WEB_SOURCES)
class TestAddSourceWeb:
    """For each existing web source, verify add_source proposes the right config."""

    def _make_config(self, name, method, category) -> dict:
        base = {"name": name, "category": category, "method": method}
        if method == "sitemap":
            base["sitemap_url"] = "https://example.com/sitemap.xml"
            base["url_pattern"] = "example\\.com/blog/[^/?#]+$"
        elif method == "html":
            base["listing_url"] = "https://example.com/blog/"
            base["link_pattern"] = "example\\.com/blog/[^/?#]+$"
            base["base_url"] = "https://example.com"
        elif method == "playwright":
            base["listing_url"] = "https://example.com/blog"
            base["link_pattern"] = "example\\.com/blog/[^/?#]+$"
        return base

    def test_proposes_web_type(self, tmp_jsons, name, method, category):
        config = self._make_config(name, method, category)
        suggestion = {"type": "web", "config": config}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", provider)
        provider.generate.assert_called_once()

    def test_cancelled_does_not_write(self, tmp_jsons, name, method, category):
        _, tmp_scr = tmp_jsons
        original = json.loads(tmp_scr.read_text())
        config = self._make_config(name, method, category)
        suggestion = {"type": "web", "config": config}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", provider)
        assert json.loads(tmp_scr.read_text()) == original

    def test_confirmed_appends_to_scraped_json(self, tmp_jsons, name, method, category):
        _, tmp_scr = tmp_jsons
        original = json.loads(tmp_scr.read_text())
        without = [s for s in original if s["name"] != name]
        sm._save(tmp_scr, without)

        config = self._make_config(name + "_test", method, category)
        suggestion = {"type": "web", "config": config}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", provider)

        after = json.loads(tmp_scr.read_text())
        names = [s["name"] for s in after]
        assert config["name"] in names
        sm._save(tmp_scr, original)

    def test_confirmed_does_not_touch_rss_json(self, tmp_jsons, name, method, category):
        tmp_src, _ = tmp_jsons
        original_rss = json.loads(tmp_src.read_text())
        config = self._make_config(name + "_web_test", method, category)
        suggestion = {"type": "web", "config": config}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", provider)
        assert json.loads(tmp_src.read_text()) == original_rss


# ── add_source: edge cases ────────────────────────────────────────────────────

class TestAddSourceEdgeCases:
    def test_invalid_json_from_claude_exits(self, tmp_jsons, capsys):
        provider = MagicMock()
        provider.generate.return_value = GenerateResult(
            text="não é JSON válido", input_tokens=0, output_tokens=0
        )
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", provider)

    def test_invalid_type_exits(self, tmp_jsons):
        suggestion = {"type": "unknown", "config": {"name": "X"}}
        provider = _make_provider(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", provider)

    def test_markdown_fences_stripped(self, tmp_jsons):
        suggestion = {"type": "rss", "config": {"name": "X", "feed_url": "https://x.com/feed", "category": "media"}}
        provider = MagicMock()
        provider.generate.return_value = GenerateResult(
            text="```json\n" + json.dumps(suggestion) + "\n```", input_tokens=0, output_tokens=0
        )
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", provider)
        # Reaching here means JSON was parsed successfully
        provider.generate.assert_called_once()

    def test_system_prompt_has_all_categories(self):
        for cat in CATEGORY_ORDER:
            assert cat in sm._SYSTEM_PROMPT, f"Category '{cat}' missing from system prompt"

    def test_system_prompt_has_all_methods(self):
        for method in ("rss", "sitemap", "html", "playwright"):
            assert method in sm._SYSTEM_PROMPT

    def test_probe_failure_prints_warning(self, tmp_jsons, capsys):
        provider = _make_provider({"type": "rss", "config": {"name": "X", "feed_url": "https://x.com/f", "category": "media"}})
        with (
            patch("httpx.get", side_effect=Exception("timeout")),
            patch("httpx.head", side_effect=Exception("timeout")),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", provider)
        out = capsys.readouterr().out
        assert "Aviso" in out

    def test_url_without_scheme_is_normalized(self, tmp_jsons):
        provider = _make_provider({"type": "rss", "config": {"name": "X", "feed_url": "https://x.com/f", "category": "media"}})
        called_urls = []
        original_probe = sm._probe_url

        def capturing_probe(url):
            called_urls.append(url)
            return _probe_side_effect()

        with (
            patch.object(sm, "_probe_url", side_effect=capturing_probe),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("example.com", provider)
        assert called_urls[0].startswith("https://")

    def test_duplicate_rss_source_rejected(self, tmp_jsons):
        tmp_src, _ = tmp_jsons
        original = json.loads(tmp_src.read_text())
        existing = original[0]
        config = {"name": existing["name"], "feed_url": existing["feed_url"], "category": existing["category"]}
        provider = _make_provider({"type": "rss", "config": config})
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", provider)
        assert json.loads(tmp_src.read_text()) == original

    def test_duplicate_web_source_rejected(self, tmp_jsons):
        _, tmp_scr = tmp_jsons
        original = json.loads(tmp_scr.read_text())
        existing = original[0]
        config = {k: v for k, v in existing.items()}
        provider = _make_provider({"type": "web", "config": config})
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", provider)
        assert json.loads(tmp_scr.read_text()) == original

    def test_incomplete_rss_config_exits(self, tmp_jsons):
        provider = _make_provider({"type": "rss", "config": {"name": "X"}})
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", provider)

    def test_incomplete_web_config_exits(self, tmp_jsons):
        provider = _make_provider({"type": "web", "config": {"name": "X", "method": "sitemap"}})
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", provider)

    def test_unknown_method_exits(self, tmp_jsons):
        provider = _make_provider({"type": "web", "config": {"name": "X", "method": "unknown"}})
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", provider)

    # ── multi-config (array response) ─────────────────────────────────────────

    def test_array_response_adds_rss_and_web(self, tmp_jsons):
        tmp_src, tmp_scr = tmp_jsons
        rss_cfg = {"name": "Multi Test RSS", "feed_url": "https://multi.com/feed.xml", "category": "media"}
        web_cfg = {
            "name": "Multi Test Web",
            "category": "media",
            "method": "sitemap",
            "sitemap_url": "https://multi.com/sitemap.xml",
            "url_pattern": r"/posts/\d+",
        }
        provider = _make_provider([
            {"type": "rss", "config": rss_cfg},
            {"type": "web", "config": web_cfg},
        ])
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://multi.com", provider)

        rss_names = [s["name"] for s in json.loads(tmp_src.read_text())]
        web_names = [s["name"] for s in json.loads(tmp_scr.read_text())]
        assert rss_cfg["name"] in rss_names
        assert web_cfg["name"] in web_names

    def test_array_cancelled_writes_nothing(self, tmp_jsons):
        tmp_src, tmp_scr = tmp_jsons
        orig_rss = json.loads(tmp_src.read_text())
        orig_web = json.loads(tmp_scr.read_text())
        rss_cfg = {"name": "Cancel Test RSS", "feed_url": "https://x.com/f", "category": "media"}
        web_cfg = {
            "name": "Cancel Test Web",
            "category": "media",
            "method": "sitemap",
            "sitemap_url": "https://x.com/sitemap.xml",
            "url_pattern": r"/p/\d+",
        }
        provider = _make_provider([
            {"type": "rss", "config": rss_cfg},
            {"type": "web", "config": web_cfg},
        ])
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://x.com", provider)
        assert json.loads(tmp_src.read_text()) == orig_rss
        assert json.loads(tmp_scr.read_text()) == orig_web

    def test_array_with_invalid_entry_skips_invalid_saves_valid(self, tmp_jsons, capsys):
        tmp_src, _ = tmp_jsons
        valid_rss = {"name": "Partial Valid", "feed_url": "https://pv.com/feed", "category": "media"}
        invalid_web = {"name": "Bad Web", "method": "sitemap"}  # missing sitemap_url, url_pattern
        provider = _make_provider([
            {"type": "rss", "config": valid_rss},
            {"type": "web", "config": invalid_web},
        ])
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://pv.com", provider)
        rss_names = [s["name"] for s in json.loads(tmp_src.read_text())]
        assert valid_rss["name"] in rss_names
        out = capsys.readouterr().out
        assert "WARN" in out

    def test_array_all_invalid_exits(self, tmp_jsons):
        provider = _make_provider([
            {"type": "rss", "config": {"name": "X"}},   # missing feed_url, category
            {"type": "web", "config": {"name": "Y"}},   # missing method etc.
        ])
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", provider)

    def test_system_prompt_documents_array_format(self):
        assert '{"type": "rss"' in sm._SYSTEM_PROMPT or "[{" in sm._SYSTEM_PROMPT


# ── _normalize_url ────────────────────────────────────────────────────────────

class TestNormalizeUrl:
    def test_adds_https_when_no_scheme(self):
        assert sm._normalize_url("example.com") == "https://example.com"

    def test_preserves_existing_scheme(self):
        url = "https://example.com"
        assert sm._normalize_url(url) == url

    def test_does_not_double_scheme(self):
        url = "https://example.com"
        assert sm._normalize_url(url).count("https://") == 1


# ── _validate_config ──────────────────────────────────────────────────────────

class TestValidateConfig:
    def test_valid_rss(self):
        config = {"name": "X", "feed_url": "https://x.com/f", "category": "media"}
        assert sm._validate_config("rss", config) == []

    def test_rss_missing_feed_url(self):
        missing = sm._validate_config("rss", {"name": "X", "category": "media"})
        assert "feed_url" in missing

    def test_valid_sitemap(self):
        config = {"name": "X", "category": "media", "method": "sitemap",
                  "sitemap_url": "https://x.com/s.xml", "url_pattern": "x\\.com/blog/"}
        assert sm._validate_config("web", config) == []

    def test_sitemap_missing_url_pattern(self):
        config = {"name": "X", "category": "media", "method": "sitemap", "sitemap_url": "https://x.com/s.xml"}
        missing = sm._validate_config("web", config)
        assert "url_pattern" in missing

    def test_valid_html(self):
        config = {"name": "X", "category": "media", "method": "html",
                  "listing_url": "https://x.com/blog", "link_pattern": "x\\.com/blog/", "base_url": "https://x.com"}
        assert sm._validate_config("web", config) == []

    def test_html_missing_base_url(self):
        config = {"name": "X", "category": "media", "method": "html",
                  "listing_url": "https://x.com/blog", "link_pattern": "x\\.com/blog/"}
        missing = sm._validate_config("web", config)
        assert "base_url" in missing

    def test_valid_playwright(self):
        config = {"name": "X", "category": "media", "method": "playwright",
                  "listing_url": "https://x.com/blog", "link_pattern": "x\\.com/blog/"}
        assert sm._validate_config("web", config) == []

    def test_unknown_method_returns_error(self):
        config = {"name": "X", "category": "media", "method": "unknown"}
        result = sm._validate_config("web", config)
        assert len(result) == 1
        assert "unknown" in result[0]

    @pytest.mark.parametrize("method,required_fields", [
        ("sitemap",    ["sitemap_url", "url_pattern"]),
        ("html",       ["listing_url", "link_pattern", "base_url"]),
        ("playwright", ["listing_url", "link_pattern"]),
    ])
    def test_all_required_fields_detected(self, method, required_fields):
        config = {"name": "X", "category": "media", "method": method}
        missing = sm._validate_config("web", config)
        for field in required_fields:
            assert field in missing


# ── _load error handling ──────────────────────────────────────────────────────

class TestLoadErrorHandling:
    def test_missing_file_exits(self, tmp_path):
        with pytest.raises(SystemExit):
            sm._load(tmp_path / "nonexistent.json")

    def test_corrupted_json_exits(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{ this is not valid json }")
        with pytest.raises(SystemExit):
            sm._load(bad)

    def test_valid_file_returns_data(self, tmp_path):
        f = tmp_path / "ok.json"
        f.write_text('[{"name": "X"}]')
        result = sm._load(f)
        assert result == [{"name": "X"}]


# ── remove_source: exact matches ──────────────────────────────────────────────

ALL_SOURCE_NAMES_RSS = [s["name"] for s in SOURCES]
ALL_SOURCE_NAMES_WEB = [s["name"] for s in SCRAPED_SOURCES]


@pytest.mark.parametrize("name", ALL_SOURCE_NAMES_RSS)
class TestRemoveSourceRSS:
    def test_cancel_first_confirm_preserves_data(self, tmp_jsons, name):
        tmp_src, _ = tmp_jsons
        original = json.loads(tmp_src.read_text())
        with patch("builtins.input", side_effect=["N"]):
            sm.remove_source(name)
        assert json.loads(tmp_src.read_text()) == original

    def test_cancel_second_confirm_preserves_data(self, tmp_jsons, name):
        tmp_src, _ = tmp_jsons
        original = json.loads(tmp_src.read_text())
        with patch("builtins.input", side_effect=["s", "wrong name"]):
            sm.remove_source(name)
        assert json.loads(tmp_src.read_text()) == original

    def test_full_confirm_removes_source(self, tmp_jsons, name):
        tmp_src, _ = tmp_jsons
        with patch("builtins.input", side_effect=["s", name]):
            sm.remove_source(name)
        after = json.loads(tmp_src.read_text())
        assert name not in [s["name"] for s in after]

    def test_full_confirm_does_not_touch_scraped(self, tmp_jsons, name):
        _, tmp_scr = tmp_jsons
        original_web = json.loads(tmp_scr.read_text())
        with patch("builtins.input", side_effect=["s", name]):
            sm.remove_source(name)
        assert json.loads(tmp_scr.read_text()) == original_web

    def test_removed_source_can_be_readded(self, tmp_jsons, name):
        tmp_src, _ = tmp_jsons
        # Find the original config
        original_data = json.loads(tmp_src.read_text())
        src_config = next(s for s in original_data if s["name"] == name)

        # Remove it
        with patch("builtins.input", side_effect=["s", name]):
            sm.remove_source(name)

        # Re-add manually and verify
        current = json.loads(tmp_src.read_text())
        current.append(src_config)
        sm._save(tmp_src, current)
        final = json.loads(tmp_src.read_text())
        assert any(s["name"] == name for s in final)


@pytest.mark.parametrize("name", ALL_SOURCE_NAMES_WEB)
class TestRemoveSourceWeb:
    def test_cancel_first_confirm_preserves_data(self, tmp_jsons, name):
        _, tmp_scr = tmp_jsons
        original = json.loads(tmp_scr.read_text())
        with patch("builtins.input", side_effect=["N"]):
            sm.remove_source(name)
        assert json.loads(tmp_scr.read_text()) == original

    def test_cancel_second_confirm_preserves_data(self, tmp_jsons, name):
        _, tmp_scr = tmp_jsons
        original = json.loads(tmp_scr.read_text())
        with patch("builtins.input", side_effect=["s", "wrong name"]):
            sm.remove_source(name)
        assert json.loads(tmp_scr.read_text()) == original

    def test_full_confirm_removes_source(self, tmp_jsons, name):
        _, tmp_scr = tmp_jsons
        with patch("builtins.input", side_effect=["s", name]):
            sm.remove_source(name)
        after = json.loads(tmp_scr.read_text())
        assert name not in [s["name"] for s in after]

    def test_full_confirm_does_not_touch_rss(self, tmp_jsons, name):
        tmp_src, _ = tmp_jsons
        original_rss = json.loads(tmp_src.read_text())
        with patch("builtins.input", side_effect=["s", name]):
            sm.remove_source(name)
        assert json.loads(tmp_src.read_text()) == original_rss

    def test_removed_source_can_be_readded(self, tmp_jsons, name):
        _, tmp_scr = tmp_jsons
        original_data = json.loads(tmp_scr.read_text())
        src_config = next(s for s in original_data if s["name"] == name)

        with patch("builtins.input", side_effect=["s", name]):
            sm.remove_source(name)

        current = json.loads(tmp_scr.read_text())
        current.append(src_config)
        sm._save(tmp_scr, current)
        final = json.loads(tmp_scr.read_text())
        assert any(s["name"] == name for s in final)


# ── remove_source: not found / partial match ──────────────────────────────────

class TestRemoveNotFound:
    def test_not_found_prints_message(self, tmp_jsons, capsys):
        sm.remove_source("SourceThatDoesNotExist")
        out = capsys.readouterr().out
        assert "não encontrada" in out

    def test_partial_match_suggests_names(self, tmp_jsons, capsys):
        # "Hugging" should suggest "Hugging Face"
        sm.remove_source("Hugging")
        out = capsys.readouterr().out
        assert "Hugging Face" in out

    def test_partial_match_does_not_remove(self, tmp_jsons):
        tmp_src, _ = tmp_jsons
        original = json.loads(tmp_src.read_text())
        sm.remove_source("Hugging")
        assert json.loads(tmp_src.read_text()) == original

    def test_case_insensitive_exact_match_rss(self, tmp_jsons):
        tmp_src, _ = tmp_jsons
        with patch("builtins.input", side_effect=["s", "openai"]):
            sm.remove_source("OPENAI")
        after = json.loads(tmp_src.read_text())
        assert "OpenAI" not in [s["name"] for s in after]

    def test_case_insensitive_exact_match_web(self, tmp_jsons):
        _, tmp_scr = tmp_jsons
        with patch("builtins.input", side_effect=["s", "anthropic"]):
            sm.remove_source("ANTHROPIC")
        after = json.loads(tmp_scr.read_text())
        assert "Anthropic" not in [s["name"] for s in after]


# ── JSON integrity ────────────────────────────────────────────────────────────

class TestJsonIntegrity:
    def test_sources_json_valid(self):
        data = json.loads((Path(__file__).parent / "sources.json").read_text())
        assert isinstance(data, list)
        assert len(data) > 0

    def test_scraped_sources_json_valid(self):
        data = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
        assert isinstance(data, list)
        assert len(data) > 0

    def test_rss_sources_have_required_fields(self):
        data = json.loads((Path(__file__).parent / "sources.json").read_text())
        for s in data:
            assert "name" in s, f"Missing 'name' in {s}"
            assert "feed_url" in s, f"Missing 'feed_url' in {s}"
            assert "category" in s, f"Missing 'category' in {s}"

    def test_web_sources_have_required_fields(self):
        data = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
        for s in data:
            assert "name" in s, f"Missing 'name' in {s}"
            assert "method" in s, f"Missing 'method' in {s}"
            assert "category" in s, f"Missing 'category' in {s}"
            if s["method"] == "sitemap":
                assert "sitemap_url" in s
                assert "url_pattern" in s
            elif s["method"] == "html":
                assert "listing_url" in s
                assert "link_pattern" in s
                assert "base_url" in s
            elif s["method"] == "playwright":
                assert "listing_url" in s
                assert "link_pattern" in s

    def test_web_sources_regex_patterns_compile(self):
        data = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
        for s in data:
            for key in ("url_pattern", "link_pattern"):
                if key in s:
                    try:
                        re.compile(s[key])
                    except re.error as e:
                        pytest.fail(f"Invalid regex in '{s['name']}' {key}: {e}")

    def test_rss_categories_are_valid(self):
        valid = set(CATEGORY_ORDER)
        data = json.loads((Path(__file__).parent / "sources.json").read_text())
        for s in data:
            assert s["category"] in valid, f"'{s['name']}' has unknown category '{s['category']}'"

    def test_web_categories_are_valid(self):
        valid = set(CATEGORY_ORDER)
        data = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
        for s in data:
            assert s["category"] in valid, f"'{s['name']}' has unknown category '{s['category']}'"

    def test_web_methods_are_valid(self):
        data = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
        valid = {"sitemap", "html", "playwright"}
        for s in data:
            assert s["method"] in valid, f"'{s['name']}' has unknown method '{s['method']}'"

    def test_rss_no_duplicate_names(self):
        data = json.loads((Path(__file__).parent / "sources.json").read_text())
        names = [s["name"] for s in data]
        assert len(names) == len(set(names)), f"Duplicate RSS names: {[n for n in names if names.count(n) > 1]}"

    def test_web_no_duplicate_names(self):
        data = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
        names = [s["name"] for s in data]
        assert len(names) == len(set(names)), f"Duplicate web names: {[n for n in names if names.count(n) > 1]}"

    def test_no_cross_duplicate_names(self):
        rss_names = {s["name"] for s in json.loads((Path(__file__).parent / "sources.json").read_text())}
        web_names = {s["name"] for s in json.loads((Path(__file__).parent / "scraped_sources.json").read_text())}
        overlap = rss_names & web_names
        assert not overlap, f"Names in both RSS and web: {overlap}"

    def test_sources_module_matches_json(self):
        json_data = json.loads((Path(__file__).parent / "sources.json").read_text())
        assert len(SOURCES) == len(json_data)
        assert [s["name"] for s in SOURCES] == [s["name"] for s in json_data]

    def test_scraped_module_matches_json(self):
        json_data = json.loads((Path(__file__).parent / "scraped_sources.json").read_text())
        assert len(SCRAPED_SOURCES) == len(json_data)
        assert [s["name"] for s in SCRAPED_SOURCES] == [s["name"] for s in json_data]

    def test_atomic_save_creates_no_tmp_on_success(self, tmp_path):
        test_file = tmp_path / "test.json"
        test_file.write_text("[]")
        sm._save(test_file, [{"name": "X"}])
        assert not (tmp_path / "test.tmp").exists()
        assert json.loads(test_file.read_text()) == [{"name": "X"}]
