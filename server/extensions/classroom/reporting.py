# SPDX-License-Identifier: AGPL-3.0-or-later
"""reporting — pure helpers for roster import, grade export, and batch clone.

Kept free of framework/manager/DB dependencies so the orchestration in the
BLL routes stays thin over unit-tested logic. Parity targets: GitHub
Classroom roster CSV import, the grades CSV download, and the batch
"clone all submissions" workflow.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence

# Accepted CSV header aliases (case-insensitive) → canonical field.
_IDENTIFIER_ALIASES = ("identifier", "id", "student_id", "sis_id", "email")
_NAME_ALIASES = ("display_name", "name", "full_name", "student_name")
_USERNAME_ALIASES = ("forgejo_username", "github_username", "username", "login")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Lower-case, hyphen-separated, filesystem/URL-safe slug."""
    slug = _SLUG_RE.sub("-", (text or "").strip().lower()).strip("-")
    return slug or "x"


def repo_name_for(assignment_slug: str, participant: str) -> str:
    """Accepted-repo name: ``<assignment-slug>-<participant>`` (both slugged)."""
    return f"{slugify(assignment_slug)}-{slugify(participant)}"


def _pick(row: Mapping[str, str], aliases: Sequence[str]) -> Optional[str]:
    lowered = {k.strip().lower(): (v or "").strip() for k, v in row.items()}
    for alias in aliases:
        if lowered.get(alias):
            return lowered[alias]
    return None


def parse_roster_csv(text: str) -> List[Dict[str, Optional[str]]]:
    """Parse a roster CSV into ``{identifier, display_name, forgejo_username}``.

    A header row is required and matched case-insensitively against known
    aliases. Rows without an identifier are skipped.
    """
    reader = csv.DictReader(io.StringIO(text))
    entries: List[Dict[str, Optional[str]]] = []
    for row in reader:
        identifier = _pick(row, _IDENTIFIER_ALIASES)
        if not identifier:
            continue
        entries.append(
            {
                "identifier": identifier,
                "display_name": _pick(row, _NAME_ALIASES),
                "forgejo_username": _pick(row, _USERNAME_ALIASES),
            }
        )
    return entries


def build_grades_csv(rows: Sequence[Mapping[str, Any]]) -> str:
    """Render assignment grades to a CSV string (GitHub Classroom shape)."""
    columns = [
        "identifier",
        "display_name",
        "forgejo_username",
        "repo_full_name",
        "status",
        "score",
        "points_possible",
        "submission_sha",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in columns})
    return buf.getvalue()


def build_submissions_manifest(base_url: str, repos: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Build a batch-clone manifest + a ready-to-run clone script.

    ``repos`` items carry ``repo_full_name``; the clone URL is derived from
    ``base_url`` (the Forgejo base). Repos not yet provisioned (no
    ``repo_full_name``) are skipped.
    """
    base = (base_url or "").rstrip("/")
    manifest: List[Dict[str, str]] = []
    lines = ["#!/usr/bin/env bash", "set -euo pipefail"]
    for repo in repos:
        full = repo.get("repo_full_name")
        if not full:
            continue
        clone_url = f"{base}/{full}.git"
        dest = str(full).replace("/", "__")
        manifest.append({"repo_full_name": str(full), "clone_url": clone_url})
        lines.append(f"git clone {clone_url} {dest}")
    return {"repos": manifest, "clone_script": "\n".join(lines) + "\n"}


__all__ = [
    "slugify",
    "repo_name_for",
    "parse_roster_csv",
    "build_grades_csv",
    "build_submissions_manifest",
]
