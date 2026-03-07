"""Environment-based configuration for tieshan-photo server."""

from __future__ import annotations

import os
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent.parent

PHOTO_SERVER_PORT: int = int(os.environ.get("PHOTO_SERVER_PORT", "8788"))

PROJECT_ROOT: Path = Path(
    os.environ.get("PROJECT_ROOT", str(_SERVER_DIR.parent.parent))
).resolve()

VAULT_ROOT: Path = Path(
    os.environ.get("VAULT_ROOT", str(PROJECT_ROOT / "Vault"))
).resolve()

FAMILY_TREE_PATH: Path = Path(
    os.environ.get("FAMILY_TREE_PATH", str(PROJECT_ROOT / "tools" / "family_tree.yaml"))
).resolve()

PHOTO_MODEL_DIR: Path = Path(
    os.environ.get("PHOTO_MODEL_DIR", str(_SERVER_DIR / "models"))
).resolve()

PHOTO_DB_PATH: Path = Path(
    os.environ.get("PHOTO_DB_PATH", str(_SERVER_DIR / "data" / "face.db"))
).resolve()

PHOTO_DET_THRESHOLD: float = float(os.environ.get("PHOTO_DET_THRESHOLD", "0.3"))

LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "info").lower()

# Photo source directories (shared with photo_manifest.py)
PHOTO_SOURCE_DIRS: list[str] = [
    "鐵山老照片from大舅舅",
    "掃描的照片",
    "整理過的照片",
    "鐵山誌圖文創作",
    "吳東興攝影贊助計畫",
    "2023李威辰個展",
    "老照片拼貼",
    "鐵峰山房唱和集素材",
    "外埔老照片專輯",
    "印出來的圖片",
    "collage",
]

IMAGE_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp",
    ".heic", ".heif",
}

# Matching thresholds (calibrated by pilot)
MATCH_HIGH: float = 0.45
MATCH_MEDIUM: float = 0.35
MATCH_LOW: float = 0.25
