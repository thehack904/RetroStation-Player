from __future__ import annotations

import logging
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

SERVICE_UNIT = "retrostation-player.service"
DEFAULT_LINES = 200
MAX_LINES = 1000
JOURNAL_CACHE_SECONDS = 10.0
_journal_cache_lock = threading.RLock()
_journal_cache: dict[tuple[int, str, str], tuple[float, dict[str, object]]] = {}


@dataclass(frozen=True)
class RuntimeLogEntry:
    timestamp: str
    level: str
    logger: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
        }


class RuntimeLogBuffer(logging.Handler):
    def __init__(self, capacity: int = MAX_LINES) -> None:
        super().__init__()
        self._entries: deque[RuntimeLogEntry] = deque(maxlen=capacity)
        self._lock = threading.RLock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
            entry = RuntimeLogEntry(
                timestamp=timestamp,
                level=record.levelname,
                logger=record.name,
                message=record.getMessage(),
            )
            with self._lock:
                self._entries.append(entry)
        except Exception:
            self.handleError(record)

    def read(self, lines: int = DEFAULT_LINES, level: str = "all", search: str = "") -> list[dict[str, str]]:
        line_limit = normalize_line_count(lines)
        level_filter = level.strip().upper()
        search_filter = search.strip().casefold()
        with self._lock:
            entries: Iterable[RuntimeLogEntry] = list(self._entries)
        if level_filter not in {"", "ALL"}:
            entries = (entry for entry in entries if entry.level == level_filter)
        if search_filter:
            entries = (
                entry for entry in entries
                if search_filter in entry.message.casefold() or search_filter in entry.logger.casefold()
            )
        return [entry.to_dict() for entry in list(entries)[-line_limit:]]


runtime_log_buffer = RuntimeLogBuffer()


def configure_logging() -> None:
    root = logging.getLogger()
    if not any(isinstance(handler, RuntimeLogBuffer) for handler in root.handlers):
        root.addHandler(runtime_log_buffer)
    if root.level > logging.INFO:
        root.setLevel(logging.INFO)


def normalize_line_count(value: int | str | None) -> int:
    try:
        lines = int(value or DEFAULT_LINES)
    except (TypeError, ValueError):
        lines = DEFAULT_LINES
    return max(1, min(MAX_LINES, lines))


def read_journal(lines: int = DEFAULT_LINES, priority: str = "all", search: str = "", *, max_lines: int = MAX_LINES) -> dict[str, object]:
    line_limit = min(normalize_line_count(lines), max(1, int(max_lines)))
    cache_key = (line_limit, priority.strip().casefold(), search.strip().casefold())
    now = time.monotonic()
    with _journal_cache_lock:
        cached = _journal_cache.get(cache_key)
        if cached and now - cached[0] < JOURNAL_CACHE_SECONDS:
            return dict(cached[1])
    command = [
        "journalctl",
        "--quiet",
        "--unit", SERVICE_UNIT,
        "--no-pager",
        "--output=short-iso-precise",
        "--lines", str(line_limit),
    ]
    priority_map = {
        "error": "err",
        "warning": "warning",
        "info": "info",
        "debug": "debug",
    }
    normalized_priority = priority.strip().casefold()
    if normalized_priority in priority_map:
        command.extend(["--priority", priority_map[normalized_priority]])

    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=8,
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "error": "journalctl is not installed", "text": ""}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "error": f"Unable to read the system journal: {exc}", "text": ""}

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        return {"available": False, "error": detail or "journalctl failed", "text": ""}

    text = completed.stdout.rstrip()
    search_filter = search.strip().casefold()
    if search_filter:
        text = "\n".join(line for line in text.splitlines() if search_filter in line.casefold())
    result: dict[str, object] = {"available": True, "error": None, "text": text}
    with _journal_cache_lock:
        _journal_cache[cache_key] = (time.monotonic(), dict(result))
    return result


def format_runtime_entries(entries: list[dict[str, str]]) -> str:
    return "\n".join(
        f"{entry['timestamp']} {entry['level']:<7} {entry['logger']}: {entry['message']}"
        for entry in entries
    )
