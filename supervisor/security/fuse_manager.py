from __future__ import annotations

import os
import shlex
import signal
import subprocess
from pathlib import Path
from typing import Iterable


class FuseManager:
    """Hardened local tool executor with timeout, sterile env, and path guards."""

    _SAFE_ENV_KEYS = (
        "PATH",
        "LANG",
        "LC_ALL",
        "TERM",
    )

    def execute_tool_safe(
        self,
        command: str | list[str] | tuple[str, ...],
        timeout: int | float,
        workspace_dir: str | os.PathLike[str],
    ) -> dict:
        workspace = Path(workspace_dir).resolve()
        if not workspace.is_dir():
            return {
                "ok": False,
                "error": "Invalid workspace_dir: directory does not exist",
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
            }

        argv = self._normalize_command(command)
        if not argv:
            return {
                "ok": False,
                "error": "Command must not be empty",
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
            }

        timeout_value = self._normalize_timeout(timeout)

        path_error = self._validate_paths(argv[1:], workspace)
        if path_error is not None:
            return {
                "ok": False,
                "error": path_error,
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
            }

        sterile_env = self._build_sterile_env()

        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(workspace),
                env=sterile_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )

            stdout_text, stderr_text = process.communicate(timeout=timeout_value)
            returncode = process.returncode
        except subprocess.TimeoutExpired as timeout_error:
            stdout_text = self._coerce_text(timeout_error.stdout)
            stderr_text = self._coerce_text(timeout_error.stderr)

            kill_error = None
            if process is not None:
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except Exception as error:
                    kill_error = str(error)

                try:
                    drained_out, drained_err = process.communicate(timeout=1)
                    if drained_out:
                        stdout_text = drained_out
                    if drained_err:
                        stderr_text = drained_err
                except Exception:
                    pass

            error_message = f"Fuse timeout after {timeout_value}s"
            if kill_error:
                error_message = f"{error_message}; kill_error={kill_error}"

            return {
                "ok": False,
                "error": error_message,
                "returncode": None,
                "stdout": self._trim_text(stdout_text),
                "stderr": self._trim_text(stderr_text),
                "timed_out": True,
            }
        except Exception as error:
            return {
                "ok": False,
                "error": f"Fuse execution failed: {error}",
                "returncode": None,
                "stdout": "",
                "stderr": "",
                "timed_out": False,
            }

        return {
            "ok": returncode == 0,
            "error": None if returncode == 0 else f"Command failed with code {returncode}",
            "returncode": returncode,
            "stdout": self._trim_text(stdout_text),
            "stderr": self._trim_text(stderr_text),
            "timed_out": False,
        }

    def _normalize_command(self, command: str | list[str] | tuple[str, ...]) -> list[str]:
        if isinstance(command, str):
            return shlex.split(command)
        if isinstance(command, tuple):
            command = list(command)
        if isinstance(command, list):
            if not all(isinstance(item, str) for item in command):
                raise TypeError("command list must contain only strings")
            return command
        raise TypeError("command must be a string or list of strings")

    def _normalize_timeout(self, timeout: int | float) -> float:
        if not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be numeric")
        timeout_value = float(timeout)
        if timeout_value <= 0:
            raise ValueError("timeout must be greater than zero")
        return timeout_value

    def _build_sterile_env(self) -> dict[str, str]:
        sterile: dict[str, str] = {}
        for key in self._SAFE_ENV_KEYS:
            value = os.environ.get(key)
            if value is not None:
                sterile[key] = value
        return sterile

    def _validate_paths(self, args: Iterable[str], workspace: Path) -> str | None:
        for token in args:
            if token.startswith("-"):
                continue
            if token.startswith("~"):
                return f"Path escape blocked: '{token}'"

            candidate = self._token_to_path(token, workspace)
            if candidate is None:
                continue

            if not self._is_within_workspace(candidate, workspace):
                return f"Path traversal blocked outside workspace: '{token}'"
        return None

    def _token_to_path(self, token: str, workspace: Path) -> Path | None:
        if token.startswith("/"):
            return Path(token).resolve(strict=False)
        if token.startswith("./") or token.startswith("../"):
            return (workspace / token).resolve(strict=False)
        if "/" in token:
            return (workspace / token).resolve(strict=False)
        return None

    def _is_within_workspace(self, candidate: Path, workspace: Path) -> bool:
        try:
            candidate.relative_to(workspace)
            return True
        except ValueError:
            return False

    def _trim_text(self, value: str) -> str:
        if len(value) <= 8000:
            return value
        return value[-8000:]

    def _coerce_text(self, value: str | bytes | None) -> str:
        if value is None:
            return ""
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value