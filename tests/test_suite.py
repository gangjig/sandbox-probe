"""Suite orchestration: selection, runner failures, verdict aggregation."""

from __future__ import annotations

import sys

from sandbox_probe.probes import default_probes, get_probe
from sandbox_probe.runners import RunResult, RunnerError
from sandbox_probe.suite import run_probe, run_suite
from conftest import ScriptedRunner, contained_handler, escaped_handler


def test_suite_runs_all_four_probes_by_default(ctx):
    runner = ScriptedRunner(contained_handler)
    report = run_suite(runner, ctx)
    assert [r.name for r in report.results] == [p.name for p in default_probes()]
    assert report.verdict == "contained"


def test_suite_reports_escaped_when_any_probe_escapes(ctx):
    def handler(argv, cwd, env, timeout):
        if argv[0] == "cat":
            return RunResult(argv=tuple(argv), returncode=0,
                             stdout=ctx.canary_token + "\n")
        return contained_handler(argv, cwd, env, timeout)

    report = run_suite(ScriptedRunner(handler), ctx)
    assert report.verdict == "escaped"
    assert report.counts()["escaped"] == 1


def test_suite_honors_probe_subset(ctx):
    runner = ScriptedRunner(contained_handler)
    report = run_suite(runner, ctx, probes=[get_probe("env-secret")])
    assert [r.name for r in report.results] == ["env-secret"]
    assert len(runner.calls) == 1


def test_runner_error_becomes_error_verdict(ctx):
    class BrokenRunner(ScriptedRunner):
        def run(self, argv, *, cwd=None, env=None, timeout=None):
            raise RunnerError("sandbox server unreachable")

    report = run_suite(BrokenRunner(lambda *a: None), ctx)
    assert report.verdict == "error"
    assert all(r.verdict == "error" for r in report.results)
    assert "unreachable" in report.results[0].detail


def test_unexpected_runner_exception_becomes_error_verdict(ctx):
    class BuggyRunner(ScriptedRunner):
        def run(self, argv, *, cwd=None, env=None, timeout=None):
            raise RuntimeError("boom")

    report = run_suite(BuggyRunner(lambda *a: None), ctx)
    assert report.verdict == "error"
    assert "RuntimeError" in report.results[0].detail


def test_runner_timeout_becomes_error_verdict(ctx):
    def handler(argv, cwd, env, timeout):
        return RunResult(argv=tuple(argv), returncode=None, timed_out=True)

    report = run_suite(ScriptedRunner(handler), ctx)
    assert report.verdict == "error"
    assert all("timed out" in r.detail for r in report.results)


def test_probe_runs_with_workspace_cwd_and_secret_env(ctx):
    runner = ScriptedRunner(contained_handler)
    run_probe(runner, get_probe("env-secret"), ctx)
    call = runner.calls[0]
    assert call["cwd"] == str(ctx.workspace_dir)
    assert call["env"] == {ctx.secret_name: ctx.secret_token}


def test_other_probes_get_empty_env(ctx):
    runner = ScriptedRunner(contained_handler)
    run_probe(runner, get_probe("read-outside-mount"), ctx)
    assert runner.calls[0]["env"] == {}


def test_timeout_is_forwarded_to_runner(ctx):
    runner = ScriptedRunner(contained_handler)
    run_probe(runner, get_probe("env-secret"), ctx, timeout=7.5)
    assert runner.calls[0]["timeout"] == 7.5


def test_durations_are_recorded(ctx):
    runner = ScriptedRunner(escaped_handler)
    report = run_suite(runner, ctx)
    assert all(r.duration_ms >= 0 for r in report.results)
    assert all(r.argv for r in report.results)


def test_error_verdict_when_no_escape_but_one_error(ctx):
    calls = {"n": 0}

    def handler(argv, cwd, env, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RunnerError("flaky")
        return contained_handler(argv, cwd, env, timeout)

    report = run_suite(ScriptedRunner(handler), ctx)
    assert report.verdict == "error"
    assert report.counts() == {"total": 4, "escaped": 0, "contained": 3,
                               "error": 1}
