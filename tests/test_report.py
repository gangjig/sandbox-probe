"""Report rendering: text format, JSON shape, verdict aggregation."""

from __future__ import annotations

import json

from sandbox_probe.report import ProbeResult, Report


def _result(name, verdict, detail="detail"):
    return ProbeResult(name=name, verdict=verdict, detail=detail,
                       duration_ms=12.34, argv=("cmd", name))


def test_empty_report_is_indeterminate():
    report = Report(results=[])
    assert report.verdict == "error"
    assert "no probes ran" in report.render_text().lower()


def test_escape_dominates_error_and_contained():
    report = Report(results=[
        _result("a", "contained"), _result("b", "error"),
        _result("c", "escaped"),
    ])
    assert report.verdict == "escaped"


def test_error_dominates_contained():
    report = Report(results=[_result("a", "contained"), _result("b", "error")])
    assert report.verdict == "error"


def test_all_contained_is_contained():
    report = Report(results=[_result("a", "contained")])
    assert report.verdict == "contained"


def test_text_report_lists_every_probe_with_verdict_tag():
    report = Report(results=[
        _result("read-outside-mount", "escaped", "read the canary"),
        _result("env-secret", "contained", "secret hidden"),
    ])
    text = report.render_text()
    assert "[escaped] read-outside-mount: read the canary" in text
    assert "[contained] env-secret: secret hidden" in text
    assert "2 probes, 1 escaped, 1 contained, 0 errored" in text
    assert "Verdict: ESCAPED" in text


def test_text_report_contained_verdict_line():
    report = Report(results=[_result("a", "contained")])
    assert "Verdict: CONTAINED - no probe escaped" in report.render_text()


def test_text_report_indeterminate_verdict_line():
    report = Report(results=[_result("a", "error")])
    text = report.render_text()
    assert "Verdict: INDETERMINATE" in text
    assert "1 probe(s) errored" in text


def test_json_report_round_trips_and_has_expected_shape():
    report = Report(results=[
        _result("read-outside-mount", "escaped", "read the canary"),
    ])
    parsed = json.loads(report.render_json())
    assert parsed["verdict"] == "escaped"
    assert parsed["summary"] == {"total": 1, "escaped": 1, "contained": 0,
                                 "error": 0}
    (entry,) = parsed["results"]
    assert entry["name"] == "read-outside-mount"
    assert entry["verdict"] == "escaped"
    assert entry["detail"] == "read the canary"
    assert entry["duration_ms"] == 12.3
    assert entry["argv"] == ["cmd", "read-outside-mount"]


def test_text_report_uses_singular_probe_for_one_result():
    report = Report(results=[_result("a", "contained")])
    assert "1 probe, 0 escaped" in report.render_text()


def test_to_dict_matches_render_json():
    report = Report(results=[_result("a", "contained")])
    assert json.loads(report.render_json()) == report.to_dict()
