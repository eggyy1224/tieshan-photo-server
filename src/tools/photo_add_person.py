"""photo_add_person — Add a new person to the recognition database."""

from __future__ import annotations

import re
from typing import Any

from .. import db, log
from ..config import FAMILY_TREE_PATH
from ..persons import save_person, _UNSET


def _is_in_family_tree(person_id: str) -> bool:
    """Check if person_id is defined in family_tree.yaml using simple text scan.

    Looks for the YAML key pattern (e.g. '  xu_tiande:' at line start under persons).
    Avoids full YAML parse which can fail on duplicate keys.
    """
    if not FAMILY_TREE_PATH.exists():
        return False
    try:
        text = FAMILY_TREE_PATH.read_text(encoding="utf-8")
        # YAML key pattern: person_id followed by colon, at indentation level
        # under 'persons:' block. Match '  person_id:' with leading whitespace.
        import re
        return bool(re.search(rf"^\s+{re.escape(person_id)}\s*:", text, re.MULTILINE))
    except OSError:
        return False


async def photo_add_person(
    person_id: str,
    display_name: str = "",
    gender: str = "",
    birth_year: int | None = None,
    aliases: list[str] | None = None,
    notes: str = "",
    clear_gender: bool = False,
    clear_birth_year: bool = False,
    clear_aliases: bool = False,
    clear_notes: bool = False,
) -> dict:
    """Add a new person or update an existing person in the face recognition database.

    The person is saved to related_persons.yaml and loaded into SQLite.

    To clear a field on an existing person, set the corresponding clear_* flag to True.
    For example, clear_gender=True removes the stored gender value.

    Args:
        person_id: Unique ID in snake_case (e.g. 'lin_qingjing'). Must start with a letter.
        display_name: Display name (e.g. '林清經'). Required for new persons, optional for updates.
        gender: 'M'/'F' or empty. Ignored if clear_gender is True.
        birth_year: Four-digit birth year (e.g. 1893), or None if unknown. Ignored if clear_birth_year is True.
        aliases: Alternative names (e.g. ['林氏清經', '清經']). Ignored if clear_aliases is True.
        notes: Free-text notes about this person. Ignored if clear_notes is True.
        clear_gender: Set True to remove existing gender value.
        clear_birth_year: Set True to remove existing birth_year value.
        clear_aliases: Set True to remove existing aliases.
        clear_notes: Set True to remove existing notes.

    Returns:
        Confirmation with person_id and display_name.
    """
    person_id = person_id.strip()
    if not person_id:
        return {"error": "MISSING_FIELDS", "message": "person_id is required"}

    if not re.fullmatch(r"[a-z][a-z0-9_]*", person_id):
        return {
            "error": "INVALID_PERSON_ID",
            "message": "person_id must be snake_case (lowercase letters, digits, underscores; start with letter)",
        }

    # Check if person already exists (DB or family_tree text scan).
    # We avoid _find_yaml_source() here because family_tree.yaml may have
    # duplicate keys that crash ruamel's strict parser.
    existing_in_db = db.get_person(person_id)
    existing_in_ft = _is_in_family_tree(person_id)
    existing = existing_in_db or existing_in_ft
    display_name = display_name.strip() if display_name else ""
    if not existing and not display_name:
        return {"error": "MISSING_FIELDS", "message": "display_name is required for new persons"}

    # Guard: refuse to update persons defined in family_tree.yaml.
    # This tool only writes to related_persons.yaml; family_tree.yaml is the
    # canonical source for direct family members and must be edited manually.
    if existing_in_ft:
        return {
            "error": "FAMILY_TREE_PROTECTED",
            "message": (
                f"{person_id} is defined in family_tree.yaml (direct family members). "
                "This tool only writes to related_persons.yaml. "
                "Edit family_tree.yaml manually to update this person."
            ),
        }

    # Build kwargs — _UNSET means "don't touch", None means "clear"
    kwargs: dict[str, Any] = {}

    if display_name:
        # Reject HTML markup to prevent stored XSS (web UI renders via innerHTML)
        if re.search(r"[<>&\"]", display_name):
            return {
                "error": "INVALID_DISPLAY_NAME",
                "message": "display_name must not contain HTML characters (<, >, &, \")",
            }
        kwargs["display_name"] = display_name

    # gender
    if clear_gender:
        kwargs["gender"] = None
    elif gender:
        g = gender.strip().lower()
        if g in ("m", "male"):
            kwargs["gender"] = "male"
        elif g in ("f", "female"):
            kwargs["gender"] = "female"
        else:
            return {"error": "INVALID_GENDER", "message": f"gender must be M/F, got {gender!r}"}

    # birth_year
    if clear_birth_year:
        kwargs["birth_year"] = None
    elif birth_year is not None:
        if not (1000 <= birth_year <= 9999):
            return {"error": "INVALID_BIRTH_YEAR", "message": "birth_year must be a 4-digit year"}
        kwargs["birth_year"] = birth_year

    # aliases
    if clear_aliases:
        kwargs["aliases"] = None
    elif aliases:
        kwargs["aliases"] = [a.strip() for a in aliases if a.strip()]

    # notes
    if clear_notes:
        kwargs["notes"] = None
    elif notes:
        kwargs["notes"] = notes.strip()

    final_name = save_person(person_id, **kwargs)

    is_new = not existing
    log.info("person saved", person_id=person_id, display_name=final_name, is_new=is_new)

    return {
        "ok": True,
        "person_id": person_id,
        "display_name": final_name,
        "is_new": is_new,
    }
