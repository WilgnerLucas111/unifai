from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
TMP_SAFE_ROOT = Path("/tmp")
TMP_SAFE_PREFIX = "unifai_"
SENSITIVE_FILES = {
    Path("/etc/shadow"),
    Path("/etc/passwd"),
}
SENSITIVE_PREFIXES = (
    Path("/proc"),
    Path("/sys"),
    Path("/dev"),
)


@dataclass(frozen=True)
class ReadFileResult:
    content: str
    start_line: int
    num_lines: int
    total_lines: int


def _is_sensitive_path(path: Path) -> bool:
    if path in SENSITIVE_FILES:
        return True
    return any(path == prefix or prefix in path.parents for prefix in SENSITIVE_PREFIXES)


def _is_workspace_path(path: Path) -> bool:
    try:
        path.relative_to(WORKSPACE_ROOT)
        return True
    except ValueError:
        return False


def _is_allowed_tmp_path(path: Path) -> bool:
    try:
        path.relative_to(TMP_SAFE_ROOT)
    except ValueError:
        return False
    return path.name.startswith(TMP_SAFE_PREFIX)


def _resolve_safe_path(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = (WORKSPACE_ROOT / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if _is_sensitive_path(candidate):
        raise PermissionError(f"Access to sensitive path is blocked: {candidate}")

    if not (_is_workspace_path(candidate) or _is_allowed_tmp_path(candidate)):
        raise PermissionError(
            f"Path traversal detected. Allowed roots: {WORKSPACE_ROOT} and {TMP_SAFE_ROOT}/{TMP_SAFE_PREFIX}*"
        )

    return candidate


def safe_read_file(path: str, offset: int = 0, limit: int | None = None) -> dict:
    if not isinstance(offset, int):
        raise TypeError("offset must be an integer")
    if limit is not None and not isinstance(limit, int):
        raise TypeError("limit must be an integer or None")

    target = _resolve_safe_path(path)
    if not target.exists():
        raise FileNotFoundError(f"File not found: {target}")
    if not target.is_file():
        raise IsADirectoryError(f"Path is not a file: {target}")

    content = target.read_text(encoding="utf-8")
    lines = content.splitlines()
    total_lines = len(lines)

    start_index = max(0, min(offset, total_lines))
    end_index = total_lines if limit is None else min(start_index + max(1, limit), total_lines)

    selected_lines = lines[start_index:end_index]
    result = ReadFileResult(
        content="\n".join(selected_lines),
        start_line=start_index + 1,
        num_lines=len(selected_lines),
        total_lines=total_lines,
    )
    return asdict(result)


if __name__ == "__main__":
    demo_path = Path(__file__).resolve().parent / "_demo_line_slice.txt"
    demo_content = "\n".join([f"line {line_number}" for line_number in range(1, 11)]) + "\n"

    try:
        demo_path.write_text(demo_content, encoding="utf-8")
        output = safe_read_file(str(demo_path), offset=2, limit=3)
        print(output)
    finally:
        if demo_path.exists():
            demo_path.unlink()
