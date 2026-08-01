"""Tests for the CI gate that enforces provider-invariance.

This script gates every pull request, so a silent failure in it would let real
drift through unnoticed -- it needs the same scrutiny as the code it guards.
"""

import pytest

from tools.check_provider_invariance import describe_divergence, main, outcomes


def _write_report(path, cases):
    """Write a minimal JUnit XML report. `cases` is [(classname, name, outcome)]."""
    body = "".join(
        f'<testcase classname="{cls}" name="{name}">'
        + ("" if outcome == "passed" else f"<{outcome} />")
        + "</testcase>"
        for cls, name, outcome in cases
    )
    path.write_text(f'<?xml version="1.0"?><testsuites><testsuite>{body}</testsuite></testsuites>', encoding="utf-8")
    return path


PASSING = [("tests.test_a", "test_one", "passed"), ("tests.test_a", "test_two", "passed")]


def test_identical_reports_pass(tmp_path):
    a = _write_report(tmp_path / "a.xml", PASSING)
    b = _write_report(tmp_path / "b.xml", PASSING)
    assert main([str(a), str(b)]) == 0


def test_a_missing_test_fails(tmp_path):
    a = _write_report(tmp_path / "a.xml", PASSING)
    b = _write_report(tmp_path / "b.xml", PASSING[:1])
    assert main([str(a), str(b)]) == 1


def test_an_extra_test_fails(tmp_path):
    a = _write_report(tmp_path / "a.xml", PASSING[:1])
    b = _write_report(tmp_path / "b.xml", PASSING)
    assert main([str(a), str(b)]) == 1


def test_a_silently_skipped_test_fails(tmp_path):
    # The motivating case: every run still exits zero, but one provider quietly
    # skipped a test. Counting alone would not catch this.
    a = _write_report(tmp_path / "a.xml", PASSING)
    b = _write_report(tmp_path / "b.xml", [PASSING[0], ("tests.test_a", "test_two", "skipped")])
    assert main([str(a), str(b)]) == 1


def test_divergence_names_the_offending_test(tmp_path):
    # "The runs differ" is not actionable; the message has to say which test.
    a = outcomes(_write_report(tmp_path / "a.xml", PASSING))
    b = outcomes(_write_report(tmp_path / "b.xml", PASSING[:1]))
    problems = describe_divergence(a, b)
    assert any("test_two" in p for p in problems)


def test_duplicate_identifier_in_baseline_is_rejected(tmp_path):
    # Overwriting silently would let a skipped-then-passed pair collapse to
    # "passed", neutralising the gate.
    dupe = _write_report(
        tmp_path / "a.xml",
        [("tests.test_a", "test_one", "skipped"), ("tests.test_a", "test_one", "passed")],
    )
    with pytest.raises(ValueError, match="duplicate testcase identifier"):
        outcomes(dupe)


def test_duplicate_identifier_in_candidate_is_rejected(tmp_path):
    _write_report(tmp_path / "a.xml", PASSING)
    dupe = _write_report(
        tmp_path / "b.xml",
        [("tests.test_a", "test_one", "skipped"), ("tests.test_a", "test_one", "passed")],
    )
    with pytest.raises(ValueError, match="duplicate testcase identifier"):
        outcomes(dupe)


def test_empty_baseline_fails_rather_than_passing_vacuously(tmp_path):
    # A report with no testcases means collection produced nothing. Exiting zero
    # there would make "no tests ran" indistinguishable from success.
    a = _write_report(tmp_path / "a.xml", [])
    b = _write_report(tmp_path / "b.xml", PASSING)
    assert main([str(a), str(b)]) == 1


def test_too_few_arguments_is_a_usage_error(tmp_path):
    assert main([str(_write_report(tmp_path / "a.xml", PASSING))]) == 2
