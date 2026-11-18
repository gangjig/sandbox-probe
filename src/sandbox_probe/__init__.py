"""sandbox-probe: does this sandbox actually contain the agent?

Run a small suite of escape probes against a runner -- a local
subprocess, or any execution boundary that implements the Runner
protocol -- and get a per-probe contained/escaped/error report.
"""

from .context import ProbeContext, temporary_context
from .probes import Probe, ProbeOutcome, Verdict, default_probes, get_probe
from .report import ProbeResult, Report
from .runners import LocalRunner, RunResult, Runner, RunnerError
from .suite import run_probe, run_suite

__version__ = "0.1.0"

__all__ = [
    "LocalRunner",
    "Probe",
    "ProbeContext",
    "ProbeOutcome",
    "ProbeResult",
    "Report",
    "RunResult",
    "Runner",
    "RunnerError",
    "Verdict",
    "__version__",
    "default_probes",
    "get_probe",
    "run_probe",
    "run_suite",
    "temporary_context",
]
