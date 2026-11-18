"""CLI: flags, exit codes, JSON output, and the real local-runner path."""

from __future__ import annotations

import json

import pytest

from sandbox_probe.cli import (
    EXIT_CONTAINED,
    EXIT_ESCAPED,
    EXIT_INDETERMINATE,
    EXIT_USAGE_ERROR,
    main,
)
from sandbox_probe.probes import default_probes
from sandbox_probe.runners import LocalRunner, RunResult, RunnerError
from conftest import ScriptedRunner, contained_handler, escaped_handler


def _factory_for(handler):
    return lambda: ScriptedRunner(handler)


def test_list_probes_prints_all_names(capsys):
    assert main(["--list-probes"]) == EXIT_CONTAINED
    out = capsys.readouterr().out
    for probe in default_probes():
        assert probe.name in out
        assert probe.description in out


def test_contained_suite_exits_zero(ctx, capsys):
    code = main([], runner_factory=_factory_for(contained_handler))
    assert code == EXIT_CONTAINED
    out = capsys.readouterr().out
    assert "Verdict: CONTAINED" in out
    assert "4 probes" in out


def test_escaped_suite_exits_two(ctx, capsys):
    code = main([], runner_factory=_factory_for(escaped_handler))
    assert code == EXIT_ESCAPED
    assert "Verdict: ESCAPED" in capsys.readouterr().out


def test_errored_suite_exits_three(capsys):
    def handler(argv, cwd, env, timeout):
        raise RunnerError("down")

    code = main([], runner_factory=_factory_for(handler))
    assert code == EXIT_INDETERMINATE
    assert "Verdict: INDETERMINATE" in capsys.readouterr().out


def test_json_output_is_valid_json(ctx, capsys):
    code = main(["--json"],
                runner_factory=_factory_for(contained_handler))
    assert code == EXIT_CONTAINED
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["verdict"] == "contained"
    assert parsed["summary"]["total"] == 4


def test_probe_flag_runs_only_the_named_probe(ctx, capsys):
    code = main(["--probe", "env-secret", "--json"],
                runner_factory=_factory_for(contained_handler))
    assert code == EXIT_CONTAINED
    parsed = json.loads(capsys.readouterr().out)
    assert [r["name"] for r in parsed["results"]] == ["env-secret"]


def test_unknown_probe_name_exits_one_with_valid_names(capsys):
    code = main(["--probe", "nope"])
    assert code == EXIT_USAGE_ERROR
    err = capsys.readouterr().err
    assert "unknown probe" in err
    assert "read-outside-mount" in err


def test_timeout_flag_is_accepted(ctx, capsys):
    code = main(["--timeout", "5"],
                runner_factory=_factory_for(contained_handler))
    assert code == EXIT_CONTAINED


def test_local_runner_end_to_end_reports_four_results(capsys):
    code = main([])
    out = capsys.readouterr().out
    assert code in (EXIT_CONTAINED, EXIT_ESCAPED, EXIT_INDETERMINATE)
    assert "4 probes" in out
    for probe in default_probes():
        assert probe.name in out


def test_local_runner_detects_shared_filesystem_env_and_network(capsys):
    """The local runner shares everything, so three probes must escape.

    The write probe is excluded: as root, permission bits do not stop the
    write, while as an unprivileged user the read-only directory holds.
    """
    main(["--json"])
    parsed = json.loads(capsys.readouterr().out)
    by_name = {r["name"]: r["verdict"] for r in parsed["results"]}
    assert by_name["read-outside-mount"] == "escaped"
    assert by_name["env-secret"] == "escaped"
    assert by_name["network-bypass"] == "escaped"
    assert by_name["write-readonly"] in ("escaped", "contained", "error")


def test_main_accepts_runner_factory_returning_local_runner(capsys):
    code = main(["--list-probes"], runner_factory=LocalRunner)
    assert code == EXIT_CONTAINED
