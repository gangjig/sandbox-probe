"""Each probe must detect escape when the runner allows it, and pass when
the runner contains it."""

from __future__ import annotations

import sys

import pytest

from sandbox_probe.context import ProbeContext
from sandbox_probe.probes import Probe, default_probes, get_probe
from sandbox_probe.runners import RunResult
from sandbox_probe.suite import run_probe
from conftest import ScriptedRunner, contained_handler, escaped_handler


def _probe(name: str) -> Probe:
    return get_probe(name)


@pytest.mark.parametrize("name", [p.name for p in default_probes()])
def test_probe_reports_contained_against_proper_sandbox(ctx, name):
    runner = ScriptedRunner(contained_handler)
    result = run_probe(runner, _probe(name), ctx)
    assert result.verdict == "contained"
    assert result.name == name


@pytest.mark.parametrize("name", [p.name for p in default_probes()])
def test_probe_reports_escaped_against_missing_boundary(ctx, name):
    runner = ScriptedRunner(escaped_handler)
    result = run_probe(runner, _probe(name), ctx)
    assert result.verdict == "escaped"
    assert result.name == name


def test_read_probe_uses_the_canary_path(fake_ctx):
    probe = _probe("read-outside-mount")
    assert probe.argv(fake_ctx) == ["cat", str(fake_ctx.canary_path)]


def test_read_probe_error_when_read_succeeds_without_token(fake_ctx):
    probe = _probe("read-outside-mount")
    result = RunResult(argv=("cat",), returncode=0, stdout="something else\n")
    assert probe.evaluate(result, fake_ctx).verdict == "error"


def test_env_probe_passes_the_secret_in_env(fake_ctx):
    probe = _probe("env-secret")
    assert probe.env(fake_ctx) == {
        fake_ctx.secret_name: fake_ctx.secret_token
    }
    assert probe.argv(fake_ctx) == ["printenv", fake_ctx.secret_name]


def test_env_probe_error_on_unexpected_output(fake_ctx):
    probe = _probe("env-secret")
    result = RunResult(argv=("printenv",), returncode=0,
                       stdout="some-other-value\n")
    assert probe.evaluate(result, fake_ctx).verdict == "error"


def test_network_probe_script_disables_proxies(fake_ctx):
    probe = _probe("network-bypass")
    argv = probe.argv(fake_ctx)
    assert argv[0] == sys.executable
    assert "ProxyHandler({})" in argv[2]
    assert fake_ctx.network_url in argv[2]


def test_network_probe_contained_detail_names_the_failure(fake_ctx):
    probe = _probe("network-bypass")
    result = RunResult(argv=("python3",), returncode=1, stderr="boom\n")
    outcome = probe.evaluate(result, fake_ctx)
    assert outcome.verdict == "contained"
    assert "boom" in outcome.detail


def test_write_probe_targets_the_readonly_dir(fake_ctx):
    probe = _probe("write-readonly")
    argv = probe.argv(fake_ctx)
    assert argv[0] == sys.executable
    assert str(fake_ctx.readonly_dir) in argv[2]


def test_write_probe_error_when_exit_zero_without_marker(fake_ctx):
    probe = _probe("write-readonly")
    result = RunResult(argv=("python3",), returncode=0, stdout="")
    assert probe.evaluate(result, fake_ctx).verdict == "error"


@pytest.mark.parametrize("name", [p.name for p in default_probes()])
def test_timeout_is_error_not_containment(fake_ctx, name):
    probe = _probe(name)
    result = RunResult(argv=("x",), returncode=None, timed_out=True)
    outcome = probe.evaluate(result, fake_ctx)
    assert outcome.verdict == "error"
    assert "timed out" in outcome.detail


def test_default_probes_are_four_unique_names():
    names = [probe.name for probe in default_probes()]
    assert names == ["read-outside-mount", "env-secret", "network-bypass",
                     "write-readonly"]
    assert len(set(names)) == 4


def test_get_probe_rejects_unknown_name():
    with pytest.raises(ValueError, match="unknown probe"):
        get_probe("no-such-probe")


def test_every_probe_has_a_description():
    for probe in default_probes():
        assert probe.description.strip()
