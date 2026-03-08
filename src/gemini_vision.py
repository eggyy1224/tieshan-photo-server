"""Gemini Flash Vision HTTP client for scene annotation.

Uses native urllib (no SDK dependency), matching the pattern in docai_context_ocr_to_md.py.
"""

from __future__ import annotations

import base64
import json
import time
import urllib.request
import urllib.error
from typing import Any, Optional

import cv2
import numpy as np

from . import log
from .config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_RPM, GEMINI_MAX_DIM


# ── Rate Limiter ────────────────────────────────────────────────────

class RateLimiter:
    """Simple RPM-based rate limiter using time.sleep."""

    def __init__(self, rpm: int) -> None:
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self._last: float = 0.0

    def wait(self) -> None:
        if self.interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self._last = time.monotonic()


_rate_limiter: Optional[RateLimiter] = None


def _get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter(GEMINI_RPM)
    return _rate_limiter


# ── Image Processing ────────────────────────────────────────────────

def resize_for_gemini(img: np.ndarray, max_dim: int = 0) -> str:
    """Resize image so longest edge <= max_dim, encode as JPEG q85, return base64.

    If already within limit, encode without resize.
    """
    if max_dim <= 0:
        max_dim = GEMINI_MAX_DIM

    h, w = img.shape[:2]
    long_edge = max(h, w)

    if long_edge > max_dim:
        scale = max_dim / long_edge
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if not ok:
        raise RuntimeError("Failed to encode image as JPEG")
    return base64.b64encode(buf.tobytes()).decode("ascii")


# ── Gemini Vision API ──────────────────────────────────────────────

_PROMPT = """你是一位臺灣歷史老照片的研究助手。請仔細觀察這張照片，以 JSON 回傳標注。

注意：
- 照片多為日治時期臺灣（1895–1945）的黑白或早期彩色
- 可能包含日文、漢文（繁體中文）文字
- 無法判斷的欄位填 null
- objects 和 texts 盡可能完整列出

欄位：
- scene_type: 場景（室內/室外/混合/不明）
- location: 地點類型（神社/學校/家屋前/田野/街道/碼頭/車站/墓地/寺廟/官署/醫院/商店街/合院埕/其他）
- architecture: 建築風格（如有可見建築）
- era_clues: 年代線索（服裝/髮型/車輛/器物/照片技術）
- spatial_desc: 空間佈局描述（人物站位、前後景、拍攝角度，2-3句）
- objects: 顯著物件清單
- texts: 可見文字 [{text, lang(zh/ja/en), position}]
- tags: 3-8 個搜尋用標籤（繁體中文）"""

_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "required": [
        "scene_type", "location", "architecture", "era_clues",
        "spatial_desc", "objects", "texts", "tags",
    ],
    "properties": {
        "scene_type": {"type": "STRING"},
        "location": {"type": "STRING"},
        "architecture": {"type": "STRING"},
        "era_clues": {"type": "STRING"},
        "spatial_desc": {"type": "STRING"},
        "objects": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "texts": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "required": ["text", "lang", "position"],
                "properties": {
                    "text": {"type": "STRING"},
                    "lang": {"type": "STRING"},
                    "position": {"type": "STRING"},
                },
            },
        },
        "tags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
    },
}


def _repair_truncated_json(text: str) -> Optional[dict[str, Any]]:
    """Attempt to parse JSON that may have been truncated by MAX_TOKENS.

    Gemini sometimes generates excessive escaped newlines (\\n) inside string
    values that exhaust the token budget, causing truncation mid-JSON.
    Strategy:
    1. Strip trailing whitespace
    2. Collapse runs of escaped newlines inside string values
    3. Try closing open JSON structures
    """
    text = text.strip()

    # Fast path: already valid
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Collapse long runs of escaped newlines (\\n\\n\\n... → \\n) inside strings
    # In raw JSON text, escaped newlines appear as literal two-char sequences: \ n
    import re
    text = re.sub(r'(\\n){3,}', r'\\n', text)    # actual \n chars in text
    text = re.sub(r'(\\\\n){3,}', r'\\\\n', text)  # literal \\n sequences

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Strip trailing incomplete content and try closing structures
    for _ in range(40):
        text = text.rstrip(" ,\n\r\t")

        # Try various closing suffixes to complete truncated JSON structures
        for suffix in (
            "",
            "}",
            "]}",
            "]}", "]}",
            '"}',
            '"]',
            '"]}',
            '"}]}',         # close string + object + array + main
            '"}]}',
            '":""}]}',
            '"}]}',
            '"}],"objects":null,"spatial_desc":null,"era_clues":null,"architecture":null,"location":null}',
        ):
            try:
                return json.loads(text + suffix)
            except json.JSONDecodeError:
                continue

        # Trim last character and retry
        if text:
            text = text[:-1]
        else:
            break

    return None


def annotate_photo(
    img_b64: str,
    model: str = "",
    api_key: str = "",
    max_retries: int = 3,
) -> dict[str, Any]:
    """Call Gemini Vision API and return structured scene annotation.

    Uses JSON mode (responseMimeType + responseSchema) for consistent output.
    Retries with linear backoff (attempt * 4s) on transient errors.
    """
    if not model:
        model = GEMINI_MODEL
    if not api_key:
        api_key = GEMINI_API_KEY
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set — check .env or environment")

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
        f":generateContent?key={api_key}"
    )

    body = {
        "contents": [
            {
                "parts": [
                    {"text": _PROMPT},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": img_b64,
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json",
            "responseSchema": _RESPONSE_SCHEMA,
        },
    }

    data = json.dumps(body).encode("utf-8")

    for attempt in range(1, max_retries + 1):
        # Respect rate limit
        _get_rate_limiter().wait()

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))

            candidate = result.get("candidates", [{}])[0]
            finish_reason = candidate.get("finishReason", "")

            # Extract text from Gemini response
            text = (
                candidate
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )

            # Try normal parse first (with strip)
            parsed = _repair_truncated_json(text)
            if parsed is not None:
                if finish_reason == "MAX_TOKENS":
                    log.warn("gemini response truncated but repaired", attempt=attempt)
                return parsed

            # Couldn't repair — treat as parse error
            raise json.JSONDecodeError(
                f"Cannot repair truncated JSON (finishReason={finish_reason})",
                text[:200], 0,
            )

        except urllib.error.HTTPError as e:
            status = e.code
            if status == 429 or status >= 500:
                wait = attempt * 4
                log.warn(
                    "gemini transient error, retrying",
                    status=status, attempt=attempt, wait=wait,
                )
                time.sleep(wait)
                continue
            # Non-retryable HTTP error
            body_text = e.read().decode("utf-8", errors="replace")[:500]
            log.error("gemini API error", status=status, body=body_text)
            raise RuntimeError(f"Gemini API error {status}: {body_text}") from e

        except (urllib.error.URLError, TimeoutError, OSError) as e:
            wait = attempt * 4
            log.warn(
                "gemini network error, retrying",
                error=str(e), attempt=attempt, wait=wait,
            )
            time.sleep(wait)
            if attempt == max_retries:
                raise RuntimeError(f"Gemini network error after {max_retries} retries: {e}") from e

        except (json.JSONDecodeError, KeyError, IndexError) as e:
            if attempt < max_retries:
                wait = attempt * 4
                log.warn(
                    "gemini response parse error, retrying",
                    error=str(e), attempt=attempt, wait=wait,
                )
                time.sleep(wait)
                continue
            log.error("gemini response parse error", error=str(e))
            raise RuntimeError(f"Failed to parse Gemini response: {e}") from e

    raise RuntimeError("Gemini API: max retries exceeded")
