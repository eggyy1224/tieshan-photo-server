"""Parse Vault photo cards to extract person annotations as ground truth anchors."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import yaml

from . import db, log
from .config import VAULT_ROOT

# Match wikilinks like [[人物/許天象]] or [[人物/許天催.md|許天催]]
_WIKILINK_RE = re.compile(r"\[\[人物/([^\]|]+?)(?:\.md)?(?:\|[^\]]+)?\]\]")

# Year extraction patterns for known_year (from photo card text)
_YEAR_EXACT = re.compile(r"\*\*(\d{4})年?\*\*")
_YEAR_RANGE = re.compile(r"(\d{4})[–\-](\d{4})")


def parse_photo_card(card_path: Path) -> Optional[dict]:
    """Parse a photo card Markdown file.

    Returns dict with keys: source_path, persons (list of display_names).
    Returns None if the file has no type: 照片卡 frontmatter.
    """
    try:
        text = card_path.read_text(encoding="utf-8")
    except OSError:
        return None

    # Parse YAML frontmatter
    if not text.startswith("---"):
        return None

    end = text.find("---", 3)
    if end < 0:
        return None

    try:
        fm = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None

    if not isinstance(fm, dict) or fm.get("type") != "照片卡":
        return None

    source_path = fm.get("source_path", "")

    # Extract person wikilinks from body
    body = text[end + 3:]
    persons = list(set(_WIKILINK_RE.findall(body)))

    return {
        "card_path": str(card_path.relative_to(VAULT_ROOT)),
        "source_path": source_path,
        "persons": persons,
    }


def load_all_photo_cards(vault_root: Path | None = None) -> list[dict]:
    """Scan all photo cards in Vault/照片/ and return parsed results."""
    vault_root = vault_root or VAULT_ROOT
    photo_dir = vault_root / "照片"

    if not photo_dir.exists():
        log.warn("photo card directory not found", path=str(photo_dir))
        return []

    cards = []
    for md_file in sorted(photo_dir.rglob("照片卡_*.md")):
        parsed = parse_photo_card(md_file)
        if parsed and parsed["persons"]:
            cards.append(parsed)

    log.info("photo cards loaded", count=len(cards))
    return cards


def create_anchors_from_cards(vault_root: Path | None = None) -> int:
    """Load photo cards and create anchor entries for annotated persons.

    This links photo card person annotations to detected face embeddings.
    Returns number of anchors created.
    """
    cards = load_all_photo_cards(vault_root)
    anchor_count = 0

    for card in cards:
        source_path = card["source_path"]
        if not source_path:
            continue

        # Find the photo in DB
        photo = db.get_photo_by_path(source_path)
        if not photo or photo["scan_status"] != "scanned":
            continue

        # Update card_path on the photo record
        db.get_conn().execute(
            "UPDATE photos SET card_path=? WHERE photo_id=?",
            (card["card_path"], photo["photo_id"]),
        )

        # Get faces for this photo
        faces = db.get_faces_for_photo(photo["photo_id"])
        if not faces:
            continue

        # For each annotated person, try to find matching person_id
        for person_name in card["persons"]:
            # Remove path components (e.g., "許天象（姑婆祖）" → search for it)
            clean_name = person_name.split("（")[0].strip()
            person = db.find_person_by_name(clean_name)
            if not person:
                log.debug("person not found in DB", name=clean_name, card=card["card_path"])
                continue

            # If only one face in photo, assign directly
            # If multiple faces, we can't auto-assign without more info
            if len(faces) == 1:
                existing_anchor = db.get_anchor_for_face(faces[0]["face_id"])
                if existing_anchor and existing_anchor["person_id"] != person["person_id"]:
                    log.warn(
                        "skip conflicting photo card anchor",
                        face_id=faces[0]["face_id"],
                        existing_person=existing_anchor["person_id"],
                        incoming_person=person["person_id"],
                        card=card["card_path"],
                    )
                    continue

                if not existing_anchor:
                    db.insert_anchor(
                        face_id=faces[0]["face_id"],
                        person_id=person["person_id"],
                        source="photo_card",
                        confidence=0.9,
                        note=f"auto from {card['card_path']}",
                    )
                    anchor_count += 1
                db.update_face_match(
                    faces[0]["face_id"],
                    person["person_id"],
                    1.0,
                    "anchor",
                )

    db.get_conn().commit()
    log.info("anchors from photo cards", created=anchor_count)
    return anchor_count


def extract_known_year(text: str) -> Optional[int]:
    """Extract a known year from photo card text.

    Priority: **YYYY年** bold marker > YYYY–YYYY range (take midpoint).
    Returns None if no year found.
    """
    m = _YEAR_EXACT.search(text)
    if m:
        return int(m.group(1))

    m = _YEAR_RANGE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        return (lo + hi) // 2

    return None


def load_known_years(vault_root: Path | None = None) -> int:
    """Scan photo cards for known years and write to photos.known_year.

    Returns number of photos updated.
    """
    vault_root = vault_root or VAULT_ROOT
    photo_dir = vault_root / "照片"

    if not photo_dir.exists():
        return 0

    conn = db.get_conn()
    updated = 0

    for md_file in sorted(photo_dir.rglob("照片卡_*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError:
            continue

        if not text.startswith("---"):
            continue

        end = text.find("---", 3)
        if end < 0:
            continue

        try:
            fm = yaml.safe_load(text[3:end])
        except yaml.YAMLError:
            continue

        if not isinstance(fm, dict) or fm.get("type") != "照片卡":
            continue

        source_path = fm.get("source_path", "")
        if not source_path:
            continue

        year = extract_known_year(text)
        if year is None:
            continue

        photo = db.get_photo_by_path(source_path)
        if not photo:
            continue

        conn.execute(
            "UPDATE photos SET known_year = ? WHERE photo_id = ?",
            (year, photo["photo_id"]),
        )
        updated += 1

    conn.commit()
    log.info("known years loaded from photo cards", updated=updated)
    return updated
