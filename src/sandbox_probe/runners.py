"""Runners: the execution boundary probes run against.

A Runner executes one command and reports what happened. The probe suite
does not care whether the runner is a local subprocess, an SSH hop, or an
HTTP call into a sandbox server: it only reads the RunResult the runner
returns. That trust is a documented residual: a runner that fabricates
results defeats the probes.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence


class RunnerError(Exception):
    """The runner itself failed (spawn error, connection error, ...)."""


@dataclass(frozen=True)
class RunResult:
    """What a runner observed when it ran one command."""

    argv: tuple[str, ...]
    returncode: int | None  # None when the run timed out
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False


class Runner:
    """Execute one command. Subclass and implement run()."""

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        raise NotImplementedError


class LocalRunner(Runner):
    """Run commands as local subprocesses.

    This is a demonstration runner, not an isolation boundary: a
    subprocess shares the filesystem, environment, and network of the
    calling process, so probes run against it should report escapes.
    That is the point: it shows the probes can detect a missing
    boundary before you point them at a real sandbox.
    """

    def run(
        self,
        argv: Sequence[str],
        *,
        cwd: str | None = None,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> RunResult:
        merged_env = dict(os.environ)
        if env:
            merged_env.update(env)
        try:
            proc = subprocess.run(
                list(argv),
                cwd=cwd,
                env=merged_env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return RunResult(
                argv=tuple(argv),
                returncode=None,
                stdout=exc.stdout or "",
                stderr=exc.stderr or "",
                timed_out=True,
            )
        except OSError as exc:
            raise RunnerError(f"could not start {argv[0]!r}: {exc}") from exc
        return RunResult(
            argv=tuple(argv),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
        )
