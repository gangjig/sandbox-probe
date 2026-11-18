"""Escape probes: commands whose outcome reveals a missing boundary.

Each probe is a command plus an assertion about its result. A probe
reports one of three verdicts:

* ``contained`` -- the boundary held: the escape attempt failed.
* ``escaped`` -- the boundary failed: the probe reached something it must
  not reach. The verdict rests on exact token evidence in the output,
  never on an exit code alone.
* ``error`` -- containment could not be determined (the command timed
  out, the runner failed, or the output was neither clear evidence of
  escape nor clear evidence of containment).

A probe that times out is an error, not evidence of containment: a hung
command proves nothing about the boundary.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable, Literal, Mapping

from .context import ProbeContext
from .runners import RunResult

Verdict = Literal["contained", "escaped", "error"]


@dataclass(frozen=True)
class ProbeOutcome:
    verdict: Verdict
    detail: str


@dataclass(frozen=True)
class Probe:
    name: str
    description: str
    build_argv: Callable[[ProbeContext], list[str]]
    evaluate: Callable[[RunResult, ProbeContext], ProbeOutcome]
    build_env: Callable[[ProbeContext], Mapping[str, str]] = field(
        default=lambda ctx: {}
    )

    def argv(self, ctx: ProbeContext) -> list[str]:
        return self.build_argv(ctx)

    def env(self, ctx: ProbeContext) -> Mapping[str, str]:
        return self.build_env(ctx)


def _timed_out(result: RunResult, probe_name: str) -> ProbeOutcome | None:
    if result.timed_out:
        return ProbeOutcome(
            "error", f"{probe_name} timed out; containment undetermined"
        )
    return None


def _evaluate_read_outside_mount(
    result: RunResult, ctx: ProbeContext
) -> ProbeOutcome:
    if outcome := _timed_out(result, "read-outside-mount"):
        return outcome
    if ctx.canary_token in result.stdout:
        return ProbeOutcome(
            "escaped",
            f"read {ctx.canary_path} outside the mount "
            f"({len(result.stdout.strip())} bytes of canary output)",
        )
    if result.returncode != 0:
        return ProbeOutcome(
            "contained",
            f"read failed with exit code {result.returncode}",
        )
    return ProbeOutcome(
        "error",
        "read succeeded but the canary token was absent from the output",
    )


def _evaluate_env_secret(result: RunResult, ctx: ProbeContext) -> ProbeOutcome:
    if outcome := _timed_out(result, "env-secret"):
        return outcome
    if ctx.secret_token in result.stdout:
        return ProbeOutcome(
            "escaped",
            f"secret {ctx.secret_name} is visible in the environment",
        )
    if result.returncode != 0 or not result.stdout.strip():
        return ProbeOutcome(
            "contained",
            f"{ctx.secret_name} is not visible in the environment",
        )
    return ProbeOutcome(
        "error",
        f"unexpected output from printenv: {result.stdout.strip()!r}",
    )


def _evaluate_network_bypass(
    result: RunResult, ctx: ProbeContext
) -> ProbeOutcome:
    if outcome := _timed_out(result, "network-bypass"):
        return outcome
    if ctx.network_token in result.stdout:
        return ProbeOutcome(
            "escaped",
            f"reached {ctx.network_url} directly, bypassing the proxy",
        )
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        reason = detail[-1] if detail else f"exit code {result.returncode}"
        return ProbeOutcome("contained", f"direct fetch failed: {reason}")
    return ProbeOutcome(
        "error",
        "fetch succeeded but the expected token was absent from the body",
    )


def _evaluate_write_readonly(
    result: RunResult, ctx: ProbeContext
) -> ProbeOutcome:
    if outcome := _timed_out(result, "write-readonly"):
        return outcome
    if result.returncode == 0 and "WROTE" in result.stdout:
        return ProbeOutcome(
            "escaped",
            f"wrote a file into read-only directory {ctx.readonly_dir}",
        )
    if result.returncode != 0:
        return ProbeOutcome(
            "contained",
            f"write failed with exit code {result.returncode}",
        )
    return ProbeOutcome(
        "error",
        "write command exited 0 but did not report success",
    )


def _network_script(ctx: ProbeContext) -> str:
    # ProxyHandler({}) disables proxies explicitly: this probe measures
    # direct reachability, not proxy configuration.
    return (
        "import sys, urllib.request\n"
        f"url = {ctx.network_url!r}\n"
        "opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
        "try:\n"
        "    sys.stdout.write(opener.open(url, timeout=5).read().decode('utf-8', 'replace'))\n"
        "except Exception as exc:\n"
        "    print(f'fetch failed: {exc}', file=sys.stderr)\n"
        "    raise SystemExit(1)\n"
    )


def _write_script(ctx: ProbeContext) -> str:
    target = str(ctx.readonly_dir / "probe-write.txt")
    return (
        f"open({target!r}, 'w').write('sandbox-probe')\n"
        "print('WROTE')\n"
    )


def default_probes() -> list[Probe]:
    """The built-in probe suite, in run order."""
    return [
        Probe(
            name="read-outside-mount",
            description="Read a file outside the mounted directory.",
            build_argv=lambda ctx: ["cat", str(ctx.canary_path)],
            evaluate=_evaluate_read_outside_mount,
        ),
        Probe(
            name="env-secret",
            description="Read a secret from the environment.",
            build_argv=lambda ctx: ["printenv", ctx.secret_name],
            build_env=lambda ctx: {ctx.secret_name: ctx.secret_token},
            evaluate=_evaluate_env_secret,
        ),
        Probe(
            name="network-bypass",
            description="Reach the network directly, bypassing the proxy.",
            build_argv=lambda ctx: [sys.executable, "-c", _network_script(ctx)],
            evaluate=_evaluate_network_bypass,
        ),
        Probe(
            name="write-readonly",
            description="Write a file into a read-only directory.",
            build_argv=lambda ctx: [sys.executable, "-c", _write_script(ctx)],
            evaluate=_evaluate_write_readonly,
        ),
    ]


def get_probe(name: str) -> Probe:
    """Look up a probe by name, raising ValueError for unknown names."""
    for probe in default_probes():
        if probe.name == name:
            return probe
    known = ", ".join(probe.name for probe in default_probes())
    raise ValueError(f"unknown probe {name!r} (known probes: {known})")
