"""Command-line entry point: run the probe suite, print the report."""

from __future__ import annotations

import argparse
import sys
from typing import Callable, Sequence

from .context import temporary_context
from .probes import default_probes, get_probe
from .runners import LocalRunner, Runner
from .suite import run_suite

EXIT_CONTAINED = 0
EXIT_USAGE_ERROR = 1
EXIT_ESCAPED = 2
EXIT_INDETERMINATE = 3

_EXIT_BY_VERDICT = {
    "contained": EXIT_CONTAINED,
    "escaped": EXIT_ESCAPED,
    "error": EXIT_INDETERMINATE,
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sandbox-probe",
        description=(
            "Run escape probes against a sandbox and report whether the "
            "sandbox actually contains the agent. By default probes run "
            "against the local runner, which shares the caller's "
            "filesystem, environment, and network -- expect escapes."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the machine-readable JSON report instead of text.",
    )
    parser.add_argument(
        "--probe",
        action="append",
        dest="probes",
        metavar="NAME",
        help="Run only this probe (repeatable). Default: run all probes.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Per-probe timeout in seconds (default 30).",
    )
    parser.add_argument(
        "--list-probes",
        action="store_true",
        help="List the available probes and exit.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    runner_factory: Callable[[], Runner] | None = None,
) -> int:
    """Run the CLI. Returns a process exit code; never raises SystemExit."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.list_probes:
        for probe in default_probes():
            print(f"{probe.name}: {probe.description}")
        return EXIT_CONTAINED

    if args.probes:
        try:
            selected = [get_probe(name) for name in args.probes]
        except ValueError as exc:
            print(f"sandbox-probe: {exc}", file=sys.stderr)
            return EXIT_USAGE_ERROR
    else:
        selected = default_probes()

    factory = runner_factory or LocalRunner
    with temporary_context() as ctx:
        report = run_suite(
            factory(), ctx, probes=selected, timeout=args.timeout
        )

    if args.json:
        print(report.render_json())
    else:
        print(report.render_text())
    return _EXIT_BY_VERDICT[report.verdict]


if __name__ == "__main__":
    raise SystemExit(main())
