"""
Полный сброс логов процесса MCP: всё, что пишет stderr, и всё через logging (root DEBUG).

stdout не трогаем — там JSON-RPC FastMCP.

Переменные окружения:
  MCP_FULL_LOG=0     — отключить файл, stderr снова в os.devnull (как раньше).
  MCP_FULL_LOG_PATH  — абсолютный или относительный путь к файлу (по умолчанию <корень_сервера>/.cursor/mcp_full.log).
"""

from __future__ import annotations

import logging
import os
import pathlib
import sys
from datetime import datetime, timezone

_FMT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)


class _StderrToFile:
    """Минимальная замена sys.stderr: каждая запись сразу уходит в файл."""

    __slots__ = ("_fp",)

    def __init__(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(path, "a", encoding="utf-8", errors="replace", buffering=1)
        self._fp.write(
            f"\n{'='*72}\n"
            f"[{datetime.now(timezone.utc).isoformat()}] MCP full log session (stderr)\n"
            f"{'='*72}\n"
        )
        self._fp.flush()

    def write(self, data: str | bytes) -> int:
        if not data:
            return 0
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        self._fp.write(data)
        self._fp.flush()
        return len(data)

    def flush(self) -> None:
        self._fp.flush()

    def fileno(self) -> int:
        return self._fp.fileno()

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True


def install_mcp_full_capture(server_dir: str) -> pathlib.Path | None:
    """
    Подключает полный лог в файл. Возвращает путь к файлу или None, если отключено.
    """
    if os.environ.get("MCP_FULL_LOG", "1").strip().lower() in {"0", "false", "no", "off"}:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
        return None

    default = pathlib.Path(server_dir) / ".cursor" / "mcp_full.log"
    path = pathlib.Path(os.environ.get("MCP_FULL_LOG_PATH", str(default))).expanduser()
    if not path.is_absolute():
        path = (pathlib.Path(server_dir) / path).resolve()
    else:
        path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    sys.stderr = _StderrToFile(path)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    for h in list(root.handlers):
        if getattr(h, "_mcp_full_marker", None) == "mcp_full":
            root.removeHandler(h)

    fh = logging.FileHandler(path, mode="a", encoding="utf-8", errors="replace")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(_FMT)
    fh._mcp_full_marker = "mcp_full"  # type: ignore[attr-defined]
    root.addHandler(fh)

    # Явно ослабляем фильтры у типичных шумных корней — всё равно уходит в файл, не в консоль Cursor.
    for name in ("chromadb", "mcp", "mem0", "httpx", "httpcore", "urllib3"):
        logging.getLogger(name).setLevel(logging.DEBUG)

    logging.getLogger("mcp_full_log").info("Full MCP logging to %s", path)
    return path
