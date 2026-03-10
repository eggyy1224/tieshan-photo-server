"""Load and persist persons via YAML (single source of truth) with SQLite sync."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import yaml
from ruamel.yaml import YAML

from . import db, log
from .config import FAMILY_TREE_PATH

RELATED_PERSONS_PATH = FAMILY_TREE_PATH.parent / "related_persons.yaml"

# Sentinel to distinguish "field not provided" from "explicitly set to None".
_UNSET: Any = object()

# Round-trip YAML instance — preserves comments, ordering, quoting, and
# indentation so that saving one person doesn't reformat unrelated entries.
_rt_yaml = YAML()
_rt_yaml.preserve_quotes = True
_rt_yaml.indent(mapping=2, sequence=4, offset=2)
_rt_yaml.best_sequence_indent = 4
_rt_yaml.best_sequence_dash_offset = 2
_rt_yaml.width = 4096  # prevent line-wrapping of flow lists
# Preserve explicit 'null' instead of emitting bare empty values.
_rt_yaml.representer.add_representer(
    type(None),
    lambda self, data: self.represent_scalar("tag:yaml.org,2002:null", "null"),
)

# Serialize all YAML read→modify→write cycles to prevent concurrent
# requests from overwriting each other's edits or corrupting the loader.
_yaml_write_lock = threading.Lock()


# ── YAML ↔ SQLite conversion ────────────────────────────────────


def _yaml_entry_to_db(person_id: str, info: dict[str, Any]) -> None:
    """Convert one YAML person entry to DB format and upsert into SQLite."""
    display_name = info.get("display_name", person_id)
    aliases = info.get("aliases")
    aliases_json = json.dumps(aliases, ensure_ascii=False) if aliases else None
    gender_raw = info.get("gender")
    gender = "M" if gender_raw == "male" else "F" if gender_raw == "female" else None
    generation = info.get("generation")
    vault_note = info.get("vault_note")

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


def _db_record_to_yaml_entry(record: dict[str, Any]) -> dict[str, Any]:
    """Convert a SQLite person record to a YAML entry dict.

    Used when migrating a DB-only person into ``related_persons.yaml``.
    """
    entry: dict[str, Any] = {"display_name": record["display_name"]}

    aliases_raw = record.get("aliases")
    if aliases_raw:
        try:
            aliases = json.loads(aliases_raw)
            entry["aliases"] = aliases if isinstance(aliases, list) else [aliases_raw]
        except (json.JSONDecodeError, ValueError):
            entry["aliases"] = [aliases_raw]

    gender = record.get("gender")
    if gender:
        entry["gender"] = "male" if gender == "M" else "female" if gender == "F" else gender

    if record.get("generation") is not None:
        entry["generation"] = record["generation"]

    if record.get("vault_note"):
        entry["vault_note"] = record["vault_note"]

    if record.get("birth_year") is not None:
        entry["birth"] = {"date": record["birth_year"]}

    return entry


# ── Internal helpers ─────────────────────────────────────────────


def _load_yaml_persons(path: Path) -> int:
    """Parse a persons YAML file and upsert into the database. Returns count."""
    if not path.exists():
        log.warn("persons file not found", path=str(path))
        return 0

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        return 0

    persons = data.get("persons") or {}
    count = 0
    for person_id, info in persons.items():
        _yaml_entry_to_db(person_id, info)
        count += 1

    return count


def _find_yaml_source(person_id: str) -> tuple[Path, Any] | None:
    """Return ``(path, parsed_data)`` for the YAML file containing *person_id*.

    Uses ruamel.yaml round-trip loader so the returned *data* object preserves
    comments and formatting.  Returns ``None`` when *person_id* is not found in
    any YAML source.

    Search order: ``related_persons.yaml`` first, then ``family_tree.yaml``.
    This matches ``load_family_tree()`` which loads related_persons last, so
    for duplicate IDs the related_persons copy is the one that wins in the DB
    after restart.
    """
    for path in (RELATED_PERSONS_PATH, FAMILY_TREE_PATH):
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = _rt_yaml.load(f)
        if not isinstance(data, dict):
            continue
        persons = data.get("persons")
        if isinstance(persons, dict) and person_id in persons:
            return path, data
    return None


def _load_related_persons_yaml() -> tuple[Path, Any]:
    """Load (or initialise) ``related_persons.yaml`` for round-trip editing."""
    yaml_path = RELATED_PERSONS_PATH
    if yaml_path.exists():
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = _rt_yaml.load(f)
        # Handle blank / non-mapping / persons: null
        if not isinstance(data, dict):
            from ruamel.yaml.comments import CommentedMap
            data = CommentedMap()
            data["meta"] = {"version": "1.0"}
            data["persons"] = CommentedMap()
        elif not isinstance(data.get("persons"), dict):
            from ruamel.yaml.comments import CommentedMap
            data["persons"] = CommentedMap()
    else:
        from ruamel.yaml.comments import CommentedMap
        data = CommentedMap()
        data["meta"] = {"version": "1.0"}
        data["persons"] = CommentedMap()
    return yaml_path, data


def _atomic_yaml_write(path: Path, data: Any) -> None:
    """Write *data* to *path* atomically via temp-file + rename.

    The temp file is created in the same directory so that ``os.rename`` is
    guaranteed to be an atomic, same-filesystem operation.
    """
    dir_path = path.parent
    fd, tmp_path = tempfile.mkstemp(dir=str(dir_path), suffix=".yaml.tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            _rt_yaml.dump(data, f)
        os.rename(tmp_path, str(path))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _merge_into_yaml_entry(
    entry: dict[str, Any],
    *,
    display_name: Any = _UNSET,
    aliases: Any = _UNSET,
    gender: Any = _UNSET,
    generation: Any = _UNSET,
    vault_note: Any = _UNSET,
    notes: Any = _UNSET,
    birth_year: Any = _UNSET,
) -> None:
    """Merge provided fields into a YAML entry dict in-place.

    All values are in YAML-native format (gender: "male"/"female", etc.).
    ``_UNSET`` fields are left unchanged.  ``None`` clears the field.

    ``vault_note`` is the Obsidian note path (e.g. ``人物/許祖.md``).
    ``notes`` is the narrative text field (e.g. historical context).
    """
    if display_name is not _UNSET:
        entry["display_name"] = display_name

    if aliases is not _UNSET:
        entry["aliases"] = aliases if aliases else []

    if gender is not _UNSET:
        entry["gender"] = gender

    if generation is not _UNSET:
        entry["generation"] = generation

    if vault_note is not _UNSET:
        entry["vault_note"] = vault_note

    if notes is not _UNSET:
        entry["notes"] = notes

    if birth_year is not _UNSET:
        birth = entry.get("birth")
        if birth is None:
            if birth_year is not None:
                entry["birth"] = {"date": birth_year}
        else:
            if birth_year is None:
                birth["date"] = None
            else:
                existing_date = birth.get("date")
                if existing_date and len(str(existing_date)) > 4:
                    # Has full date like "1874-10-13" — replace year prefix,
                    # keep month/day suffix.
                    birth["date"] = str(birth_year) + str(existing_date)[4:]
                else:
                    # Year-only or null — write as int to match original style.
                    birth["date"] = birth_year


# ── Public API ───────────────────────────────────────────────────


def save_person(
    person_id: str,
    *,
    display_name: Any = _UNSET,
    aliases: Any = _UNSET,
    gender: Any = _UNSET,
    generation: Any = _UNSET,
    vault_note: Any = _UNSET,
    notes: Any = _UNSET,
    birth_year: Any = _UNSET,
) -> str:
    """Create or update a person.  Writes to YAML first, then syncs to SQLite.

    All field values use **YAML-native format**:
    - ``gender``: ``"male"`` / ``"female"`` / ``None``
    - ``aliases``: ``list[str]`` / ``None``
    - ``birth_year``: ``int`` / ``None``  (stored as ``birth.date`` in YAML)
    - ``vault_note``: Obsidian note path (e.g. ``人物/許祖.md``)
    - ``notes``: narrative text (e.g. historical context)

    ``_UNSET`` fields are preserved from the existing entry.
    ``None`` explicitly clears a field.

    Returns the final ``display_name``.
    """
    with _yaml_write_lock:
        result = _find_yaml_source(person_id)

        if result is not None:
            # ── Existing YAML entry — update in place ──
            yaml_path, data = result
            entry = data["persons"][person_id]
        else:
            # ── Not in YAML — add to related_persons.yaml ──
            yaml_path, data = _load_related_persons_yaml()

            # Seed from existing DB record if available (DB-only person)
            existing_db = db.get_person(person_id)
            if existing_db:
                entry = _db_record_to_yaml_entry(existing_db)
            else:
                # Brand-new person
                dn = display_name if display_name is not _UNSET else person_id
                entry = {"display_name": dn}

            data["persons"][person_id] = entry

        # Merge provided fields into the entry
        _merge_into_yaml_entry(
            entry,
            display_name=display_name,
            aliases=aliases,
            gender=gender,
            generation=generation,
            vault_note=vault_note,
            notes=notes,
            birth_year=birth_year,
        )

        # Write YAML atomically
        _atomic_yaml_write(yaml_path, data)

        # Sync this entry to SQLite (single conversion path)
        _yaml_entry_to_db(person_id, entry)

        final_name = entry.get("display_name", person_id)
        log.info("person saved", person_id=person_id, path=str(yaml_path))
        return str(final_name)


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
