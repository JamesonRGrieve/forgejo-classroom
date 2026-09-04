# SPDX-License-Identifier: AGPL-3.0-or-later
"""autograde — autograding config, scoring, and injected CI artifacts.

Parity with GitHub Classroom autograding: a teacher defines test cases
(preset kinds input/output, run-command), and on every student push a
Forgejo Actions workflow runs them, computes a score, and reports it back
to the classroom API.

Three artifacts are injected into each accepted repository on provisioning:

- ``.forgejo/workflows/autograde.yml`` — the Actions workflow (fixed).
- ``.classroom/tests.json``           — the assignment's test specs (data).
- ``.classroom/grade.py``             — a stdlib-only grader (fixed) that
  runs the tests, scores them, and POSTs the result to
  ``$CLASSROOM_API_URL/v1/grading_run/report`` (or prints it in dry-run
  when ``CLASSROOM_API_URL`` is unset).

The comparison/scoring logic here is the server-side canonical copy and is
unit tested; the injected grader is a standalone CI artifact (it cannot
import this package inside the student's runner) and is verified by
executing it as a subprocess in dry-run mode.
"""

from __future__ import annotations

import json
import re
from typing import List, Literal, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

Comparison = Literal["included", "exact", "regex"]
"""How a test's captured stdout is compared to its expected output."""

# Paths of the artifacts injected into each accepted repository.
WORKFLOW_PATH = ".forgejo/workflows/autograde.yml"
TESTS_PATH = ".classroom/tests.json"
GRADER_PATH = ".classroom/grade.py"

# The default runner label; teachers may edit the injected workflow.
_RUNNER_LABEL = "ubuntu-latest"


class AutogradeTest(BaseModel):
    """One autograding test case (mirrors GitHub Classroom test presets)."""

    name: str = Field(..., description="Human-readable test name")
    setup: Optional[str] = Field(None, description="Shell run once before the test")
    run: str = Field(..., description="Shell command whose stdout is graded")
    input: Optional[str] = Field(None, description="stdin fed to the run command")
    expected_output: Optional[str] = Field(None, description="Expected stdout")
    comparison: Comparison = Field("included", description="included|exact|regex")
    timeout: int = Field(10, description="Per-test timeout in seconds")
    points: float = Field(1.0, description="Points awarded when the test passes")


class AutogradeConfig(BaseModel):
    """The full set of tests for an assignment."""

    tests: List[AutogradeTest] = Field(default_factory=list)

    @property
    def points_possible(self) -> float:
        return sum(t.points for t in self.tests)


def compare_output(actual: str, expected: str, comparison: Comparison) -> bool:
    """Compare captured stdout to the expected value.

    - ``included``: expected (trimmed) appears somewhere in actual.
    - ``exact``: actual and expected match after trailing-whitespace trim.
    - ``regex``: expected is a regex searched against actual.
    """
    actual = actual or ""
    expected = expected or ""
    if comparison == "exact":
        return actual.strip() == expected.strip()
    if comparison == "regex":
        return re.search(expected, actual) is not None
    # included (default)
    return expected.strip() in actual


def score_results(results: Sequence[Mapping[str, object]]) -> Tuple[float, float]:
    """Sum earned and possible points over per-test results.

    Each result must carry ``points`` (float) and ``passed`` (bool).
    """
    earned = 0.0
    possible = 0.0
    for r in results:
        points = float(r.get("points", 0.0))  # type: ignore[arg-type]
        possible += points
        if bool(r.get("passed", False)):
            earned += points
    return earned, possible


def overall_status(earned: float, possible: float) -> str:
    """Map a score to a GradingRun status (passed only when full marks)."""
    if possible <= 0:
        return "error"
    return "passed" if earned >= possible else "failed"


def generate_tests_json(
    tests: Sequence[Mapping[str, object]],
    protected_paths: Optional[Sequence[str]] = None,
) -> str:
    """Serialize test specs to the ``tests.json`` injected into the repo.

    ``protected_paths`` are glob patterns the student must not modify; the
    grader fails the run and zeroes the score if any match a changed file.
    """
    fields = ("name", "setup", "run", "input", "expected_output", "comparison", "timeout", "points")
    cleaned = [{k: t.get(k) for k in fields if t.get(k) is not None} for t in tests]
    payload: dict = {"tests": cleaned}
    if protected_paths:
        payload["protected_paths"] = [p for p in protected_paths if p]
    return json.dumps(payload, indent=2, sort_keys=True)


def parse_protected_paths(raw: Optional[str]) -> List[str]:
    """Split a comma/newline-separated protected-paths string into globs."""
    if not raw:
        return []
    parts = re.split(r"[,\n]", raw)
    return [p.strip() for p in parts if p.strip()]


def generate_workflow_yaml() -> str:
    """The fixed Forgejo Actions workflow injected into each repo.

    No teacher-controlled interpolation (avoids YAML injection); the
    dynamic test specs live in ``tests.json`` (JSON), not here.
    """
    return (
        "name: Autograde\n"
        "on:\n"
        "  push:\n"
        "  workflow_dispatch:\n"
        "jobs:\n"
        "  autograde:\n"
        f"    runs-on: {_RUNNER_LABEL}\n"
        "    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/setup-python@v5\n"
        "        with:\n"
        "          python-version: '3.x'\n"
        "      - name: Run autograder\n"
        "        env:\n"
        "          CLASSROOM_API_URL: ${{ secrets.CLASSROOM_API_URL }}\n"
        "          CLASSROOM_REPORT_TOKEN: ${{ secrets.CLASSROOM_REPORT_TOKEN }}\n"
        "        run: python .classroom/grade.py\n"
    )


def generate_grader_script() -> str:
    """The stdlib-only grader injected as ``.classroom/grade.py``.

    Reads ``.classroom/tests.json``, runs each test, compares stdout,
    computes the score, and reports it. In dry-run (no ``CLASSROOM_API_URL``)
    it prints the JSON report to stdout instead of POSTing — which is how
    the test suite verifies it end-to-end.
    """
    return _GRADER_SCRIPT


# The injected grader. Standalone (stdlib only) because it runs inside the
# student's CI runner where this package is not importable. Kept in sync
# with compare_output/score_results above; the subprocess test guards drift.
_GRADER_SCRIPT = r'''#!/usr/bin/env python3
"""Classroom autograder (injected). Runs tests.json and reports the score."""
import fnmatch
import json
import os
import re
import subprocess
import sys
import urllib.request

TESTS_FILE = os.environ.get("CLASSROOM_TESTS", ".classroom/tests.json")


def protected_violations(patterns):
    """Return student-changed files matching a protected glob (empty if none)."""
    if not patterns:
        return []
    try:
        root = subprocess.run(
            ["git", "rev-list", "--max-parents=0", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).stdout.decode().strip().splitlines()
        base = root[-1] if root else None
        if not base:
            return []
        changed = subprocess.run(
            ["git", "diff", "--name-only", base, "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=30,
        ).stdout.decode().splitlines()
    except Exception:
        return []
    hits = []
    for path in changed:
        if any(fnmatch.fnmatch(path, pat) for pat in patterns):
            hits.append(path)
    return hits


def compare(actual, expected, comparison):
    actual = actual or ""
    expected = expected or ""
    if comparison == "exact":
        return actual.strip() == expected.strip()
    if comparison == "regex":
        return re.search(expected, actual) is not None
    return expected.strip() in actual


def run_test(test):
    points = float(test.get("points", 1.0))
    result = {"name": test.get("name", "test"), "points": points, "passed": False}
    setup = test.get("setup")
    try:
        if setup:
            subprocess.run(setup, shell=True, check=True, timeout=test.get("timeout", 10))
        proc = subprocess.run(
            test["run"],
            shell=True,
            input=(test.get("input") or "").encode(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=test.get("timeout", 10),
        )
        actual = proc.stdout.decode("utf-8", "replace")
        result["output"] = actual[:4000]
        if test.get("expected_output") is None:
            result["passed"] = proc.returncode == 0
        else:
            result["passed"] = compare(actual, test["expected_output"], test.get("comparison", "included"))
    except subprocess.TimeoutExpired:
        result["output"] = "TIMEOUT"
    except Exception as exc:  # report failures as a non-passing test, never crash
        result["output"] = "ERROR: %s" % exc
    return result


def main():
    with open(TESTS_FILE) as fh:
        config = json.load(fh)
    results = [run_test(t) for t in config.get("tests", [])]
    earned = sum(r["points"] for r in results if r["passed"])
    possible = sum(r["points"] for r in results)
    violations = protected_violations(config.get("protected_paths", []))
    if violations:
        earned = 0
        status = "failed"
    else:
        status = "error" if possible <= 0 else ("passed" if earned >= possible else "failed")
    report = {
        "repo_full_name": os.environ.get("GITHUB_REPOSITORY", ""),
        "commit_sha": os.environ.get("GITHUB_SHA", ""),
        "score": earned,
        "points_possible": possible,
        "status": status,
        "log_url": os.environ.get("CLASSROOM_LOG_URL", ""),
        "tests": results,
        "protected_violations": violations,
    }
    api = os.environ.get("CLASSROOM_API_URL")
    token = os.environ.get("CLASSROOM_REPORT_TOKEN", "")
    if not api:
        print(json.dumps(report, indent=2, sort_keys=True))
        return
    req = urllib.request.Request(
        api.rstrip("/") + "/v1/grading_run/report",
        data=json.dumps(report).encode(),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        sys.stdout.write("reported: %s\n" % resp.status)


if __name__ == "__main__":
    main()
'''


__all__ = [
    "Comparison",
    "AutogradeTest",
    "AutogradeConfig",
    "compare_output",
    "score_results",
    "overall_status",
    "generate_tests_json",
    "parse_protected_paths",
    "generate_workflow_yaml",
    "generate_grader_script",
    "WORKFLOW_PATH",
    "TESTS_PATH",
    "GRADER_PATH",
]
