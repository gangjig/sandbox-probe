"""LocalRunner: real subprocess execution, capture, timeout, spawn errors."""

from __future__ import annotations

import sys

import pytest

from sandbox_probe.runners import LocalRunner, RunnerError


def test_runs_command_and_captures_stdout():
    result = LocalRunner().run([sys.executable, "-c", "print('hello')"])
    assert result.returncode == 0
    assert result.stdout == "hello\n"
    assert result.stderr == ""
    assert result.timed_out is False


def test_captures_stderr_and_nonzero_exit():
    result = LocalRunner().run(
        [sys.executable, "-c", "import sys; print('oops', file=sys.stderr); "
         "raise SystemExit(3)"]
    )
    assert result.returncode == 3
    assert result.stderr == "oops\n"


def test_env_override_is_passed_through():
    result = LocalRunner().run(
        [sys.executable, "-c", "import os; print(os.environ['PROBE_MARKER'])"],
        env={"PROBE_MARKER": "marker-value"},
    )
    assert result.returncode == 0
    assert result.stdout == "marker-value\n"


def test_cwd_is_honored(tmp_path):
    result = LocalRunner().run(
        [sys.executable, "-c", "import os; print(os.getcwd())"],
        cwd=str(tmp_path),
    )
    assert result.stdout.strip() == str(tmp_path)


def test_timeout_reports_timed_out_with_no_returncode():
    result = LocalRunner().run(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout=0.2,
    )
    assert result.timed_out is True
    assert result.returncode is None


def test_missing_executable_raises_runner_error():
    with pytest.raises(RunnerError, match="could not start"):
        LocalRunner().run(["definitely-not-a-real-command-xyz"])


def test_argv_is_recorded_on_the_result():
    argv = [sys.executable, "-c", "pass"]
    result = LocalRunner().run(argv)
    assert result.argv == tuple(argv)
