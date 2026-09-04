# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the autograding engine.

Pure comparison/scoring logic is tested directly; the injected grader
artifact is verified by executing it as a real subprocess in dry-run mode
(no network, no mocks) so the generated script's behavior is proven.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "autograde_test")

from zephyrex.extensions.classroom.autograde import (
    AutogradeConfig,
    AutogradeTest,
    compare_output,
    generate_grader_script,
    generate_tests_json,
    generate_workflow_yaml,
    overall_status,
    parse_protected_paths,
    score_results,
)


class TestCompareOutput:
    def test_exact_ignores_trailing_whitespace(self):
        assert compare_output("42\n", "42", "exact") is True
        assert compare_output("42x", "42", "exact") is False

    def test_included_substring(self):
        assert compare_output("the answer is 42", "42", "included") is True
        assert compare_output("nope", "42", "included") is False

    def test_regex(self):
        assert compare_output("result: 42", r"result: \d+", "regex") is True
        assert compare_output("result: xx", r"result: \d+", "regex") is False


class TestScoring:
    def test_score_results_sums_earned_and_possible(self):
        results = [
            {"points": 2.0, "passed": True},
            {"points": 3.0, "passed": False},
            {"points": 1.0, "passed": True},
        ]
        earned, possible = score_results(results)
        assert earned == 3.0
        assert possible == 6.0

    def test_overall_status(self):
        assert overall_status(6.0, 6.0) == "passed"
        assert overall_status(3.0, 6.0) == "failed"
        assert overall_status(0.0, 0.0) == "error"


class TestConfigModel:
    def test_points_possible(self):
        cfg = AutogradeConfig(
            tests=[
                AutogradeTest(name="a", run="echo 1", points=2.0),
                AutogradeTest(name="b", run="echo 2", points=3.0),
            ]
        )
        assert cfg.points_possible == 5.0

    def test_comparison_rejects_unknown(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            AutogradeTest(name="a", run="echo", comparison="fuzzy")


class TestArtifacts:
    def test_tests_json_drops_none_and_is_valid_json(self):
        payload = generate_tests_json(
            [
                {
                    "name": "t1",
                    "run": "echo hi",
                    "expected_output": "hi",
                    "comparison": "included",
                    "points": 1.0,
                    "setup": None,
                }
            ]
        )
        data = json.loads(payload)
        assert data["tests"][0]["name"] == "t1"
        assert "setup" not in data["tests"][0]  # None dropped

    def test_workflow_yaml_has_key_steps(self):
        yml = generate_workflow_yaml()
        assert "name: Autograde" in yml
        assert "actions/checkout@v4" in yml
        assert "python .classroom/grade.py" in yml
        assert "CLASSROOM_REPORT_TOKEN" in yml

    def test_grader_script_compiles(self):
        compile(generate_grader_script(), "grade.py", "exec")


class TestGraderSubprocess:
    """Execute the generated grader against a real temp repo in dry-run."""

    def _write_repo(self, tmp_path: Path, tests: list) -> Path:
        classroom = tmp_path / ".classroom"
        classroom.mkdir(parents=True)
        (classroom / "grade.py").write_text(generate_grader_script())
        (classroom / "tests.json").write_text(generate_tests_json(tests))
        return tmp_path

    def _run(self, repo: Path):
        env = dict(os.environ)
        env.pop("CLASSROOM_API_URL", None)  # dry-run: print instead of POST
        env["GITHUB_REPOSITORY"] = "org/repo"
        env["GITHUB_SHA"] = "deadbeef"
        proc = subprocess.run(
            [sys.executable, ".classroom/grade.py"],
            cwd=repo,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=60,
        )
        return proc

    def test_all_tests_pass_full_score(self, tmp_path):
        repo = self._write_repo(
            tmp_path,
            [
                {
                    "name": "echo",
                    "run": "echo hello",
                    "expected_output": "hello",
                    "comparison": "included",
                    "points": 2.0,
                },
                {"name": "exit0", "run": "true", "points": 1.0},
            ],
        )
        proc = self._run(repo)
        assert proc.returncode == 0, proc.stdout.decode()
        report = json.loads(proc.stdout.decode())
        assert report["score"] == 3.0
        assert report["points_possible"] == 3.0
        assert report["status"] == "passed"
        assert report["repo_full_name"] == "org/repo"
        assert report["commit_sha"] == "deadbeef"

    def test_failing_test_partial_score(self, tmp_path):
        repo = self._write_repo(
            tmp_path,
            [
                {"name": "pass", "run": "echo hi", "expected_output": "hi", "comparison": "included", "points": 2.0},
                {"name": "fail", "run": "echo nope", "expected_output": "yes", "comparison": "exact", "points": 3.0},
            ],
        )
        proc = self._run(repo)
        report = json.loads(proc.stdout.decode())
        assert report["score"] == 2.0
        assert report["points_possible"] == 5.0
        assert report["status"] == "failed"

    def test_input_is_fed_to_stdin(self, tmp_path):
        repo = self._write_repo(
            tmp_path,
            [
                {
                    "name": "cat",
                    "run": "cat",
                    "input": "ping",
                    "expected_output": "ping",
                    "comparison": "exact",
                    "points": 1.0,
                }
            ],
        )
        proc = self._run(repo)
        report = json.loads(proc.stdout.decode())
        assert report["score"] == 1.0


class TestProtectedPaths:
    def test_parse_protected_paths(self):
        assert parse_protected_paths("tests/**, .classroom/**\nMakefile") == [
            "tests/**",
            ".classroom/**",
            "Makefile",
        ]
        assert parse_protected_paths(None) == []
        assert parse_protected_paths("") == []

    def test_tests_json_includes_protected(self):
        payload = json.loads(generate_tests_json([{"name": "t", "run": "true", "points": 1.0}], ["tests/**"]))
        assert payload["protected_paths"] == ["tests/**"]

    def test_grader_fails_on_protected_violation(self, tmp_path):
        import subprocess as sp

        repo = tmp_path
        git = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false"]
        sp.run(["git", "init", "-q", str(repo)], check=True, timeout=30)
        tests_dir = repo / "tests"
        tests_dir.mkdir()
        (tests_dir / "secret.py").write_text("# original protected\n")
        (repo / "solution.py").write_text("print('hi')\n")
        sp.run([*git, "add", "-A"], cwd=repo, check=True, timeout=30)
        sp.run([*git, "commit", "-q", "-m", "init"], cwd=repo, check=True, timeout=30)
        # Student tampers with a protected file.
        (tests_dir / "secret.py").write_text("# tampered\n")
        sp.run([*git, "add", "-A"], cwd=repo, check=True, timeout=30)
        sp.run([*git, "commit", "-q", "-m", "tamper"], cwd=repo, check=True, timeout=30)

        classroom = repo / ".classroom"
        classroom.mkdir()
        (classroom / "grade.py").write_text(generate_grader_script())
        (classroom / "tests.json").write_text(
            generate_tests_json(
                [{"name": "runs", "run": "python solution.py", "expected_output": "hi", "points": 5.0}], ["tests/**"]
            )
        )
        env = dict(os.environ)
        env.pop("CLASSROOM_API_URL", None)
        env["GITHUB_REPOSITORY"] = "org/repo"
        env["GITHUB_SHA"] = "deadbeef"
        proc = sp.run(
            [sys.executable, ".classroom/grade.py"],
            cwd=repo,
            env=env,
            stdout=sp.PIPE,
            stderr=sp.STDOUT,
            timeout=60,
        )
        report = json.loads(proc.stdout.decode())
        assert report["protected_violations"] == ["tests/secret.py"]
        assert report["score"] == 0
        assert report["status"] == "failed"
