"""JSON lines logger for tieshan-photo server."""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from .config import LOG_LEVEL

_LEVELS = {"debug": 0, "info": 1, "warn": 2, "error": 3}
_MIN_LEVEL = _LEVELS.get(LOG_LEVEL, 1)


def _emit(level: str, msg: str, **extra: Any) -> None:
    if _LEVELS.get(level, 1) < _MIN_LEVEL:
        return
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "level": level,
        "msg": msg,
        **extra,
    }
    print(json.dumps(record, ensure_ascii=False), file=sys.stderr, flush=True)


def debug(msg: str, **kw: Any) -> None:
    _emit("debug", msg, **kw)


def info(msg: str, **kw: Any) -> None:
    _emit("info", msg, **kw)


def warn(msg: str, **kw: Any) -> None:
    _emit("warn", msg, **kw)


def error(msg: str, **kw: Any) -> None:
    _emit("error", msg, **kw)
