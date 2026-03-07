"""Tests for photo card parsing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from src.photo_cards import parse_photo_card, _WIKILINK_RE


class TestWikilinkRegex:
    def test_basic_link(self):
        matches = _WIKILINK_RE.findall("text [[人物/許天催]] more")
        assert matches == ["許天催"]

    def test_link_with_md_extension(self):
        matches = _WIKILINK_RE.findall("[[人物/許天催.md]]")
        assert matches == ["許天催"]

    def test_link_with_alias(self):
        matches = _WIKILINK_RE.findall("[[人物/許錫玉（姑婆祖）.md|許錫玉]]")
        assert matches == ["許錫玉（姑婆祖）"]

    def test_link_with_parentheses_in_name(self):
        matches = _WIKILINK_RE.findall("[[人物/許陳允（大安港陳氏）]]")
        assert matches == ["許陳允（大安港陳氏）"]

    def test_non_person_link_ignored(self):
        matches = _WIKILINK_RE.findall("[[事件/戴潮春事件]] [[人物/許天催]]")
        assert matches == ["許天催"]

    def test_multiple_links(self):
        text = "| [[人物/許天象]] | [[人物/許雲陽]] | [[人物/許錫玉（姑婆祖）]] |"
        matches = _WIKILINK_RE.findall(text)
        assert set(matches) == {"許天象", "許雲陽", "許錫玉（姑婆祖）"}


class TestParsePhotoCard:
    def _write_card(self, tmp_path: Path, content: str) -> Path:
        card = tmp_path / "test_card.md"
        card.write_text(content, encoding="utf-8")
        return card

    def test_valid_card(self, tmp_path):
        content = """---
type: 照片卡
status: draft
source_path: test/photo.jpg
---

# Test Card

前排 [[人物/許天催]] 和 [[人物/許天象]]
"""
        card = self._write_card(tmp_path, content)
        # Override VAULT_ROOT for testing
        import src.photo_cards as pc
        original_root = pc.VAULT_ROOT
        pc.VAULT_ROOT = tmp_path
        try:
            result = parse_photo_card(card)
        finally:
            pc.VAULT_ROOT = original_root

        assert result is not None
        assert result["source_path"] == "test/photo.jpg"
        assert set(result["persons"]) == {"許天催", "許天象"}

    def test_non_photo_card_returns_none(self, tmp_path):
        content = """---
type: 人物卡
---

# Not a photo card
"""
        card = self._write_card(tmp_path, content)
        assert parse_photo_card(card) is None

    def test_no_frontmatter_returns_none(self, tmp_path):
        card = self._write_card(tmp_path, "# Just a note\nNo frontmatter here.")
        assert parse_photo_card(card) is None
