#!/usr/bin/env python3
"""Assert that GATEKEEPER_PROVIDER made no difference to what the test suite ran.

Three green pytest runs prove each configuration passes. They do NOT prove the
three runs executed the same tests: a provider-dependent skip, or a collection
difference caused by import-time environment reads, leaves every run green while
quietly shrinking coverage. This repo has already hit that class of drift once --
an ambient GATEKEEPER_PROVIDER=kimi turned 12 previously-passing tests red -- so
the invariant is worth enforcing rather than asserting in a comment.

Compares per-test identity and outcome across JUnit XML reports and reports the
specific divergence, since "the runs differ" is not actionable on its own.

Usage:
    check_provider_invariance.py BASELINE.xml OTHER.xml [OTHER.xml ...]
"""

from __future__ import annotations

import sys
from pathlib import Path
from xml.etree import ElementTree

# A testcase carries at most one of these as a child element; absence means it
# passed. Kept as a set so an unexpected future tag does not silently read as
# "passed".
OUTCOME_TAGS = {"error", "failure", "skipped"}


def outcomes(report: Path) -> dict[str, str]:
    """Map "classname::name" -> outcome for every testcase in a JUnit report."""
    root = ElementTree.parse(report).getroot()
    results: dict[str, str] = {}
    for case in root.iter("testcase"):
        test_id = f"{case.get('classname', '')}::{case.get('name', '')}"
        if test_id in results:
            # Silently overwriting would defeat the whole check: a report holding
            # the same id twice -- skipped then passed -- would collapse to
            # "passed" and the skip would never be reported. A guard that can be
            # quietly neutralised is worse than no guard, so fail loudly instead.
            raise ValueError(f"{report} contains duplicate testcase identifier: {test_id}")
        outcome = next((child.tag for child in case if child.tag in OUTCOME_TAGS), "passed")
        results[test_id] = outcome
    return results


def describe_divergence(baseline: dict[str, str], other: dict[str, str]) -> list[str]:
    """Human-readable reasons the two runs differ. Empty list means identical."""
    problems = []
    for test_id in sorted(set(baseline) - set(other)):
        problems.append(f"  missing (ran in baseline, not here): {test_id}")
    for test_id in sorted(set(other) - set(baseline)):
        problems.append(f"  extra (ran here, not in baseline):   {test_id}")
    for test_id in sorted(set(baseline) & set(other)):
        if baseline[test_id] != other[test_id]:
            problems.append(f"  outcome changed {baseline[test_id]} -> {other[test_id]}: {test_id}")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    baseline_path = Path(argv[0])
    baseline = outcomes(baseline_path)
    if not baseline:
        # An empty report means collection produced nothing -- a green exit code
        # would otherwise make "no tests ran" look like success.
        print(f"FAIL: {baseline_path} contains no testcases", file=sys.stderr)
        return 1

    failed = False
    for candidate in argv[1:]:
        problems = describe_divergence(baseline, outcomes(Path(candidate)))
        if problems:
            failed = True
            print(f"FAIL: {candidate} did not run the same tests as {baseline_path}", file=sys.stderr)
            print("\n".join(problems), file=sys.stderr)

    if failed:
        return 1

    print(f"OK: {len(baseline)} tests, identical across {len(argv)} provider configurations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
