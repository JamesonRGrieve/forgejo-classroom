# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tests for the pure reporting/import/export helpers."""

import csv
import io
import os

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "reporting_test")

from zephyrex.extensions.classroom.reporting import (
    build_grades_csv,
    build_submissions_manifest,
    parse_roster_csv,
    repo_name_for,
    slugify,
)


class TestSlug:
    def test_slugify_normalizes(self):
        assert slugify("CMPUT 174!") == "cmput-174"
        assert slugify("  Ada Lovelace  ") == "ada-lovelace"
        assert slugify("") == "x"

    def test_repo_name_for(self):
        assert repo_name_for("lab-1", "Ada Lovelace") == "lab-1-ada-lovelace"


class TestRosterCsv:
    def test_parses_aliased_headers(self):
        entries = parse_roster_csv("student_id,name,github_username\n1234,Ada Lovelace,ada\n5678,Alan Turing,\n")
        assert len(entries) == 2
        assert entries[0] == {
            "identifier": "1234",
            "display_name": "Ada Lovelace",
            "forgejo_username": "ada",
        }
        assert entries[1]["forgejo_username"] is None

    def test_skips_rows_without_identifier(self):
        entries = parse_roster_csv("identifier,name\n,Nobody\nX1,Somebody\n")
        assert len(entries) == 1
        assert entries[0]["identifier"] == "X1"

    def test_forgejo_username_alias(self):
        entries = parse_roster_csv("email,forgejo_username\na@b.ca,ada\n")
        assert entries[0]["identifier"] == "a@b.ca"
        assert entries[0]["forgejo_username"] == "ada"


class TestGradesCsv:
    def test_headers_and_row(self):
        out = build_grades_csv(
            [
                {
                    "identifier": "1234",
                    "display_name": "Ada",
                    "forgejo_username": "ada",
                    "repo_full_name": "cmput174-f26/lab1-ada",
                    "status": "graded",
                    "score": 87.5,
                    "points_possible": 100,
                    "submission_sha": "deadbeef",
                    "extra": "ignored",
                }
            ]
        )
        rows = list(csv.DictReader(io.StringIO(out)))
        assert rows[0]["identifier"] == "1234"
        assert rows[0]["score"] == "87.5"
        assert "extra" not in rows[0]


class TestSubmissionsManifest:
    def test_manifest_and_clone_script(self):
        m = build_submissions_manifest(
            "https://git.example.edu/",
            [
                {"repo_full_name": "cmput174-f26/lab1-ada"},
                {"repo_full_name": None},  # unprovisioned, skipped
                {"repo_full_name": "cmput174-f26/lab1-alan"},
            ],
        )
        assert len(m["repos"]) == 2
        assert m["repos"][0]["clone_url"] == "https://git.example.edu/cmput174-f26/lab1-ada.git"
        assert "git clone https://git.example.edu/cmput174-f26/lab1-ada.git cmput174-f26__lab1-ada" in m["clone_script"]
        assert m["clone_script"].startswith("#!/usr/bin/env bash")
