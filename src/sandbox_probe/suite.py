"""The probe suite: run probes against a runner, collect a report."""

from __future__ import annotations

import time
from dataclasses import dataclass

from .context import ProbeContext
from .probes import Probe, ProbeOutcome, default_probes
from .report import ProbeResult, Report
from .runners import Runner, RunnerError


def run_probe(
    runner: Runner,
    probe: Probe,
    ctx: ProbeContext,
    *,
    timeout: float | None = None,
) -> ProbeResult:
    """Run one probe. A failing runner yields an error verdict, never a crash."""
    started = time.monotonic()
    argv = probe.argv(ctx)
    try:
        result = runner.run(
            argv,
            cwd=str(ctx.workspace_dir),
            env=probe.env(ctx),
            timeout=timeout,
        )
    except RunnerError as exc:
        outcome = ProbeOutcome("error", f"runner failed: {exc}")
    except Exception as exc:  # a buggy runner must not kill the suite
        outcome = ProbeOutcome(
            "error", f"runner raised {type(exc).__name__}: {exc}"
        )
    else:
        outcome = probe.evaluate(result, ctx)
    return ProbeResult(
        name=probe.name,
        verdict=outcome.verdict,
        detail=outcome.detail,
        duration_ms=(time.monotonic() - started) * 1000.0,
        argv=tuple(argv),
    )


def run_suite(
    runner: Runner,
    ctx: ProbeContext,
    *,
    probes: list[Probe] | None = None,
    timeout: float | None = None,
) -> Report:
    """Run the selected probes (all four by default) and return a Report."""
    selected = list(probes) if probes is not None else default_probes()
    results = [run_probe(runner, probe, ctx, timeout=timeout) for probe in selected]
    return Report(results=results)
