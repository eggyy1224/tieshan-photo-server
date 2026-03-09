"""Shared test fixtures — ensures DB isolation across all test files."""

from __future__ import annotations

import os
import tempfile

# Must be set before ANY src import
_tmpdir = tempfile.mkdtemp()
_test_db_path = os.path.join(_tmpdir, "test.db")
os.environ["PHOTO_DB_PATH"] = _test_db_path

import pytest

from src import db


@pytest.fixture(autouse=True)
def fresh_db():
    """Ensure a completely fresh database for each test."""
    db.close()
    if os.path.exists(_test_db_path):
        os.remove(_test_db_path)
    db._conn = None
    yield
    db.close()
