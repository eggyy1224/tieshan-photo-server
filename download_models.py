#!/usr/bin/env python3
"""Download InsightFace buffalo_l model pack (~300MB).

Usage:
    python download_models.py

The model is downloaded to ./models/buffalo_l/ via InsightFace's built-in
model downloader. If the model already exists, this is a no-op.

Manual download (if automatic fails):
    1. Go to https://github.com/deepinsight/insightface/releases
    2. Download buffalo_l.zip from the model zoo
    3. Extract to ./models/buffalo_l/
"""

from __future__ import annotations

import sys
from pathlib import Path

MODEL_DIR = Path(__file__).parent / "models"


def main() -> int:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    buffalo_dir = MODEL_DIR / "buffalo_l"
    if buffalo_dir.exists() and any(buffalo_dir.glob("*.onnx")):
        print(f"Model already exists at {buffalo_dir}")
        print(f"  Files: {[f.name for f in buffalo_dir.glob('*.onnx')]}")
        return 0

    print("Downloading InsightFace buffalo_l model pack...")
    print(f"  Destination: {MODEL_DIR}")
    print("  This may take a few minutes (~300MB)...")
    print()

    try:
        import insightface
        app = insightface.app.FaceAnalysis(
            name="buffalo_l",
            root=str(MODEL_DIR),
            providers=["CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=(640, 640))
        print()
        print("Download complete!")
        print(f"  Model location: {MODEL_DIR / 'buffalo_l'}")
        return 0
    except ImportError:
        print("ERROR: insightface not installed.", file=sys.stderr)
        print("  Run: uv sync", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        print()
        print("Manual download instructions:")
        print("  1. Visit https://github.com/deepinsight/insightface/releases")
        print("  2. Download buffalo_l.zip from model zoo")
        print(f"  3. Extract to {MODEL_DIR / 'buffalo_l'}/")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
