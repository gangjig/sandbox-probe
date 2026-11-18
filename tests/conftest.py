"""Shared fakes: scripted runners simulating contained and escaped sandboxes.

The handlers are context-independent: the escaped handler performs the
escape for real (reads the file, returns the env value, fetches the URL),
which is exactly what a missing boundary means. That lets the same fakes
drive both direct suite tests and CLI tests, where the CLI builds its own
context with fresh random tokens.
"""

from __future__ import annotations

import re
import urllib.request
from pathlib import Path
from typing import Callable, Mapping, Sequence

import pytest

from sandbox_probe.context import ProbeContext, temporary_context
from sandbox_probe.runners import RunResult, Runner


class ScriptedRunner(Runner):
    """A runner driven by a handler function; records every call."""

    def __init__(self, handler: Callable[..., RunResult]) -> None:
        self.handler = handler
        self.calls: list[dict] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        self.calls.append(
            {"argv": list(argv), "cwd": cwd, "env": dict(env or {}),
             "timeout": timeout}
        )
        return self.handler(list(argv), cwd, env, timeout)


def _result(argv: list[str], returncode: int, stdout: str = "",
            stderr: str = "") -> RunResult:
    return RunResult(argv=tuple(argv), returncode=returncode,
                     stdout=stdout, stderr=stderr)


def contained_handler(argv, cwd, env, timeout):
    """Simulate a proper sandbox: every escape attempt fails."""
    if argv[0] == "cat":
        return _result(argv, 1, "",
                       f"cat: {argv[1]}: No such file or directory")
    if argv[0] == "printenv":
        return _result(argv, 1, "")
    if argv[0].endswith("python3") or "python" in argv[0]:
        if "urllib" in argv[2]:
            return _result(argv, 1, "",
                           "fetch failed: [Errno 111] Connection refused")
        return _result(argv, 1, "",
                       "PermissionError: [Errno 13] Permission denied")
    raise AssertionError(f"unexpected argv: {argv}")


def escaped_handler(argv, cwd, env, timeout):
    """Simulate a missing boundary: every escape attempt succeeds."""
    if argv[0] == "cat":
        try:
            content = Path(argv[1]).read_text(encoding="utf-8")
        except OSError as exc:
            return _result(argv, 1, "", str(exc))
        return _result(argv, 0, content)
    if argv[0] == "printenv":
        return _result(argv, 0, (env or {}).get(argv[1], "") + "\n")
    if argv[0].endswith("python3") or "python" in argv[0]:
        if "urllib" in argv[2]:
            match = re.search(r"url = '([^']+)'", argv[2])
            assert match, "network probe script has no URL literal"
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}))
            body = opener.open(match.group(1), timeout=5).read().decode("utf-8")
            return _result(argv, 0, body)
        return _result(argv, 0, "WROTE\n")
    raise AssertionError(f"unexpected argv: {argv}")


@pytest.fixture()
def ctx():
    """A real planted context (temp dirs + loopback canary server)."""
    with temporary_context() as context:
        yield context


@pytest.fixture()
def fake_ctx(tmp_path: Path):
    """A context with invented paths; for pure evaluation tests."""
    return ProbeContext(
        workspace_dir=tmp_path / "workspace",
        canary_path=tmp_path / "outside" / "canary.txt",
        canary_token="canary-token-abc",
        readonly_dir=tmp_path / "readonly",
        secret_name="SANDBOX_PROBE_SECRET",
        secret_token="secret-token-def",
        network_url="http://127.0.0.1:9/canary",
        network_token="network-token-ghi",
    )
