"""Load persons from family_tree.yaml and related_persons.yaml into the database."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import db, log
from .config import FAMILY_TREE_PATH

RELATED_PERSONS_PATH = FAMILY_TREE_PATH.parent / "related_persons.yaml"


def _load_yaml_persons(path: Path) -> int:
    """Parse a persons YAML file and upsert into the database. Returns count."""
    if not path.exists():
        log.warn("persons file not found", path=str(path))
        return 0

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    persons = data.get("persons", {})
    count = 0

    for person_id, info in persons.items():
        display_name = info.get("display_name", person_id)
        aliases = info.get("aliases")
        aliases_json = json.dumps(aliases, ensure_ascii=False) if aliases else None
        gender_raw = info.get("gender")
        gender = "M" if gender_raw == "male" else "F" if gender_raw == "female" else None
        generation = info.get("generation")
        vault_note = info.get("vault_note")

        # Extract birth year from birth.date (formats: "1874-10-13", "1851", null)
        birth_info = info.get("birth") or {}
        raw = birth_info.get("date")
        birth_year = int(str(raw)[:4]) if raw else None

        db.upsert_person(
            person_id=person_id,
            display_name=display_name,
            aliases=aliases_json,
            gender=gender,
            generation=generation,
            vault_note=vault_note,
            birth_year=birth_year,
        )
        count += 1

    return count


def load_family_tree(path: Path | None = None) -> int:
    """Load family_tree.yaml + related_persons.yaml into the database.

    Returns total number of persons loaded.
    """
    family_count = _load_yaml_persons(path or FAMILY_TREE_PATH)
    log.info("family tree loaded", persons=family_count, path=str(path or FAMILY_TREE_PATH))

    related_count = _load_yaml_persons(RELATED_PERSONS_PATH)
    if related_count:
        log.info("related persons loaded", persons=related_count, path=str(RELATED_PERSONS_PATH))

    return family_count + related_count
