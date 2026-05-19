"""Tests for source_manager: list, add, remove — all 58 sources."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import source_manager as sm
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


def _make_client(response_json: dict) -> MagicMock:
    """Build a fake Anthropic client that returns a fixed JSON string."""
    client = MagicMock()
    content = MagicMock()
    content.text = json.dumps(response_json)
    client.messages.create.return_value = MagicMock(content=[content])
    return client


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
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", client)
        client.messages.create.assert_called_once()

    def test_cancelled_does_not_write(self, tmp_jsons, name, feed_url, category):
        tmp_src, _ = tmp_jsons
        original = json.loads(tmp_src.read_text())
        suggestion = {"type": "rss", "config": {"name": name, "feed_url": feed_url, "category": category}}
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", client)
        assert json.loads(tmp_src.read_text()) == original

    def test_confirmed_appends_to_sources_json(self, tmp_jsons, name, feed_url, category):
        tmp_src, _ = tmp_jsons
        # Remove the source first so we can re-add it
        original = json.loads(tmp_src.read_text())
        without = [s for s in original if s["name"] != name]
        sm._save(tmp_src, without)

        config = {"name": name + "_test", "feed_url": feed_url, "category": category}
        suggestion = {"type": "rss", "config": config}
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", client)

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
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect(rss_links=[feed_url])),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", client)
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
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", client)
        client.messages.create.assert_called_once()

    def test_cancelled_does_not_write(self, tmp_jsons, name, method, category):
        _, tmp_scr = tmp_jsons
        original = json.loads(tmp_scr.read_text())
        config = self._make_config(name, method, category)
        suggestion = {"type": "web", "config": config}
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", client)
        assert json.loads(tmp_scr.read_text()) == original

    def test_confirmed_appends_to_scraped_json(self, tmp_jsons, name, method, category):
        _, tmp_scr = tmp_jsons
        original = json.loads(tmp_scr.read_text())
        without = [s for s in original if s["name"] != name]
        sm._save(tmp_scr, without)

        config = self._make_config(name + "_test", method, category)
        suggestion = {"type": "web", "config": config}
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", client)

        after = json.loads(tmp_scr.read_text())
        names = [s["name"] for s in after]
        assert config["name"] in names
        sm._save(tmp_scr, original)

    def test_confirmed_does_not_touch_rss_json(self, tmp_jsons, name, method, category):
        tmp_src, _ = tmp_jsons
        original_rss = json.loads(tmp_src.read_text())
        config = self._make_config(name + "_web_test", method, category)
        suggestion = {"type": "web", "config": config}
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="s"),
        ):
            sm.add_source("https://example.com", client)
        assert json.loads(tmp_src.read_text()) == original_rss


# ── add_source: edge cases ────────────────────────────────────────────────────

class TestAddSourceEdgeCases:
    def test_invalid_json_from_claude_exits(self, tmp_jsons, capsys):
        client = MagicMock()
        content = MagicMock()
        content.text = "não é JSON válido"
        client.messages.create.return_value = MagicMock(content=[content])
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", client)

    def test_invalid_type_exits(self, tmp_jsons):
        suggestion = {"type": "unknown", "config": {"name": "X"}}
        client = _make_client(suggestion)
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            pytest.raises(SystemExit),
        ):
            sm.add_source("https://example.com", client)

    def test_markdown_fences_stripped(self, tmp_jsons):
        suggestion = {"type": "rss", "config": {"name": "X", "feed_url": "https://x.com/feed", "category": "media"}}
        client = MagicMock()
        content = MagicMock()
        content.text = "```json\n" + json.dumps(suggestion) + "\n```"
        client.messages.create.return_value = MagicMock(content=[content])
        with (
            patch.object(sm, "_probe_url", return_value=_probe_side_effect()),
            patch("builtins.input", return_value="N"),
        ):
            sm.add_source("https://example.com", client)
        # Reaching here means JSON was parsed successfully
        client.messages.create.assert_called_once()

    def test_system_prompt_has_all_categories(self):
        for cat in CATEGORY_ORDER:
            assert cat in sm._SYSTEM_PROMPT, f"Category '{cat}' missing from system prompt"

    def test_system_prompt_has_all_methods(self):
        for method in ("rss", "sitemap", "html", "playwright"):
            assert method in sm._SYSTEM_PROMPT


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
