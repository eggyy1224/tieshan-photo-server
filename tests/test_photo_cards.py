"""Tests for photo card parsing."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src import db
from src.photo_cards import create_anchors_from_cards, parse_photo_card, _WIKILINK_RE


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


class TestCreateAnchorsFromCards:
    def test_updates_face_assignment_when_anchor_created(self, tmp_path):
        photo_dir = tmp_path / "照片"
        photo_dir.mkdir()
        card = photo_dir / "照片卡_test.md"
        card.write_text(
            """---
type: 照片卡
source_path: test/photo.jpg
---

前排 [[人物/許天催]]
""",
            encoding="utf-8",
        )

        db.upsert_person("xu_tiancui", "許天催")
        pid = db.upsert_photo("test/photo.jpg", "test", "photo.jpg")
        db.mark_scanned(pid, 1)
        emb = np.random.randn(512).astype(np.float32)
        fid = db.insert_face(pid, (0.1, 0.2, 0.3, 0.4), 0.9, emb)

        import src.photo_cards as pc

        original_root = pc.VAULT_ROOT
        pc.VAULT_ROOT = tmp_path
        try:
            created = create_anchors_from_cards()
        finally:
            pc.VAULT_ROOT = original_root

        assert created == 1
        face = db.get_faces_for_photo(pid)[0]
        assert face["face_id"] == fid
        assert face["person_id"] == "xu_tiancui"
        assert face["match_method"] == "anchor"
