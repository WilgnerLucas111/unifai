#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from supervisor.tools.file_ops import safe_read_file


def main() -> int:
    target = Path("/tmp/unifai_dummy_log.txt")

    try:
        lines = [f"line {idx}" for idx in range(1, 101)]
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")

        page = safe_read_file(str(target), offset=10, limit=5)
        page_lines = page.get("content", "").splitlines()

        assert len(page_lines) == 5, f"expected 5 lines, got {len(page_lines)}"
        assert page.get("start_line") == 11, f"expected start_line=11, got {page.get('start_line')}"
        assert page.get("total_lines") == 100, f"expected total_lines=100, got {page.get('total_lines')}"

        try:
            safe_read_file("/etc/passwd")
        except Exception:
            pass
        else:
            raise AssertionError("expected protected path access to be blocked for /etc/passwd")

        print("[PASS] File pagination smoke test passed.")
        return 0
    except Exception as exc:
        print(f"[FAIL] File pagination smoke test failed: {exc}")
        return 1
    finally:
        if target.exists():
            target.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
