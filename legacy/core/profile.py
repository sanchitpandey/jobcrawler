from __future__ import annotations

from pathlib import Path


def load_key_value_profile(path: str | Path) -> dict[str, str]:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"{file_path} not found")

    result: dict[str, str] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush_current() -> None:
        nonlocal current_key, current_lines
        if current_key is not None:
            result[current_key] = "\n".join(line.rstrip() for line in current_lines).strip()
        current_key = None
        current_lines = []

    for raw_line in file_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if current_key is not None and (line.startswith("  ") or line.startswith("\t")):
            current_lines.append(stripped)
            continue

        if ":" not in line:
            continue

        flush_current()
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value in {">", "|"}:
            current_key = key
            current_lines = []
            continue

        result[key] = value.strip('"')

    flush_current()
    return result


def load_profile_text(*paths: str | Path) -> str:
    parts: list[str] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.exists():
            parts.append(path.read_text(encoding="utf-8").strip())
    return "\n\n".join(part for part in parts if part)
