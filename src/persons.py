"""Load persons from family_tree.yaml into the database."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import db, log
from .config import FAMILY_TREE_PATH


def load_family_tree(path: Path | None = None) -> int:
    """Parse family_tree.yaml and upsert all persons into the database.

    Returns number of persons loaded.
    """
    path = path or FAMILY_TREE_PATH
    if not path.exists():
        log.warn("family_tree.yaml not found", path=str(path))
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

        db.upsert_person(
            person_id=person_id,
            display_name=display_name,
            aliases=aliases_json,
            gender=gender,
            generation=generation,
            vault_note=vault_note,
        )
        count += 1

    log.info("family tree loaded", persons=count, path=str(path))
    return count
