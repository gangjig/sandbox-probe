"""Report: per-probe results, an overall verdict, and rendering."""

from __future__ import annotations

import json
from dataclasses import dataclass

from .probes import Verdict


@dataclass(frozen=True)
class ProbeResult:
    name: str
    verdict: Verdict
    detail: str
    duration_ms: float
    argv: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "verdict": self.verdict,
            "detail": self.detail,
            "duration_ms": round(self.duration_ms, 1),
            "argv": list(self.argv),
        }


@dataclass(frozen=True)
class Report:
    results: tuple[ProbeResult, ...] | list[ProbeResult]

    @property
    def verdict(self) -> Verdict:
        """Escape dominates error dominates contained.

        A report with no results is an error: nothing was probed, so no
        claim about containment can be made.
        """
        if not self.results:
            return "error"
        if any(result.verdict == "escaped" for result in self.results):
            return "escaped"
        if any(result.verdict == "error" for result in self.results):
            return "error"
        return "contained"

    def counts(self) -> dict[str, int]:
        return {
            "total": len(self.results),
            "escaped": sum(1 for r in self.results if r.verdict == "escaped"),
            "contained": sum(1 for r in self.results if r.verdict == "contained"),
            "error": sum(1 for r in self.results if r.verdict == "error"),
        }

    def to_dict(self) -> dict:
        counts = self.counts()
        return {
            "verdict": self.verdict,
            "summary": counts,
            "results": [result.to_dict() for result in self.results],
        }

    def render_text(self) -> str:
        counts = self.counts()
        total = counts["total"]
        noun = "probe" if total == 1 else "probes"
        lines = [
            f"Sandbox probe report: {total} {noun}, "
            f"{counts['escaped']} escaped, {counts['contained']} contained, "
            f"{counts['error']} errored",
            self._verdict_line(counts),
            "",
        ]
        for result in self.results:
            lines.append(f"  [{result.verdict}] {result.name}: {result.detail}")
        return "\n".join(lines)

    def _verdict_line(self, counts: dict[str, int]) -> str:
        if self.verdict == "escaped":
            return (
                f"Verdict: ESCAPED - {counts['escaped']} probe(s) escaped "
                "the sandbox"
            )
        if self.verdict == "error":
            if counts["total"] == 0:
                return "Verdict: INDETERMINATE - no probes ran"
            return (
                f"Verdict: INDETERMINATE - {counts['error']} probe(s) "
                "errored, none escaped"
            )
        return "Verdict: CONTAINED - no probe escaped"

    def render_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
