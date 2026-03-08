"""Environment-based configuration for tieshan-photo server."""

from __future__ import annotations

import os
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(env_path: Path) -> None:
    """Lightweight .env loader — no python-dotenv dependency.

    Parses KEY=VALUE lines (skips comments and blank lines).
    Only sets variables not already in os.environ (no overwrite).
    """
    if not env_path.is_file():
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


# Load project-root .env before reading any config values
_load_dotenv(_SERVER_DIR.parent.parent / ".env")

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

# Gemini Vision configuration (scene annotation)
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_RPM: int = int(os.environ.get("GEMINI_RPM", "14"))
GEMINI_MAX_DIM: int = int(os.environ.get("GEMINI_MAX_DIM", "1024"))

# SigLIP image embedding (semantic search)
EMBED_MODEL: str = os.environ.get("EMBED_MODEL", "google/siglip-base-patch16-384")
EMBED_DIM: int = int(os.environ.get("EMBED_DIM", "768"))
EMBED_DEVICE: str = os.environ.get("EMBED_DEVICE", "auto")  # auto → mps if available, else cpu
