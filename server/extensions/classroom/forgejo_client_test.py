# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ForgejoClient request construction.

The HTTP boundary is an isolated utility, so it is exercised with a
recording fake that captures (verb, url, json, headers) and returns canned
JSON — no live Forgejo, no business-logic mocking.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "forgejo_client_test")

from zephyrex.extensions.classroom.forgejo_client import (
    ForgejoClient,
    ForgejoConfigError,
)


class RecordingHTTP:
    """Captures every call and returns a canned dict."""

    def __init__(self, response=None):
        self.calls = []
        self._response = response if response is not None else {"ok": True}

    def _record(self, verb, url, **kw):
        self.calls.append({"verb": verb, "url": url, **kw})
        return self._response

    def get(self, url, **kw):
        return self._record("GET", url, **kw)

    def post(self, url, **kw):
        return self._record("POST", url, **kw)

    def put(self, url, **kw):
        return self._record("PUT", url, **kw)

    def patch(self, url, **kw):
        return self._record("PATCH", url, **kw)

    def delete(self, url, **kw):
        return self._record("DELETE", url, **kw)


def make_client(response=None):
    http = RecordingHTTP(response)
    client = ForgejoClient(
        base_url="https://git.example.edu/",
        token="secret-token",
        http=http,
    )
    return client, http


class TestConfig:
    def test_base_url_trailing_slash_stripped(self):
        client, _ = make_client()
        assert client.base_url == "https://git.example.edu"
        assert client.api == "https://git.example.edu/api/v1"

    def test_configured_true_when_url_and_token(self):
        client, _ = make_client()
        assert client.configured is True

    def test_unconfigured_raises(self):
        client = ForgejoClient(base_url="", token="", http=RecordingHTTP())
        assert client.configured is False
        with pytest.raises(ForgejoConfigError):
            client.get_repo("org", "repo")

    def test_auth_header_uses_token_scheme(self):
        client, http = make_client()
        client.get_repo("org", "repo")
        assert http.calls[0]["headers"]["Authorization"] == "token secret-token"


class TestRepoOperations:
    def test_generate_repo_from_template(self):
        client, http = make_client()
        client.generate_repo_from_template(
            "cmput174-f26",
            "lab1-starter",
            owner="cmput174-f26",
            name="lab1-ada",
            private=True,
            description="Lab 1 for Ada",
        )
        call = http.calls[0]
        assert call["verb"] == "POST"
        assert call["url"] == ("https://git.example.edu/api/v1/repos/" "cmput174-f26/lab1-starter/generate")
        assert call["json"] == {
            "owner": "cmput174-f26",
            "name": "lab1-ada",
            "private": True,
            "description": "Lab 1 for Ada",
            "git_content": True,
        }

    def test_get_repo(self):
        client, http = make_client()
        client.get_repo("cmput174-f26", "lab1-ada")
        assert http.calls[0]["verb"] == "GET"
        assert http.calls[0]["url"].endswith("/repos/cmput174-f26/lab1-ada")

    def test_add_collaborator_default_write(self):
        client, http = make_client()
        client.add_collaborator("cmput174-f26", "lab1-ada", "ada")
        call = http.calls[0]
        assert call["verb"] == "PUT"
        assert call["url"].endswith("/repos/cmput174-f26/lab1-ada/collaborators/ada")
        assert call["json"] == {"permission": "write"}


class TestFileInjection:
    def test_put_file_with_branch(self):
        client, http = make_client()
        client.put_file(
            "cmput174-f26",
            "lab1-ada",
            ".forgejo/workflows/autograde.yml",
            content_b64="YWJj",
            message="Add autograding",
            branch="main",
        )
        call = http.calls[0]
        assert call["verb"] == "POST"
        assert call["url"].endswith("/repos/cmput174-f26/lab1-ada/contents/.forgejo/workflows/autograde.yml")
        assert call["json"] == {
            "content": "YWJj",
            "message": "Add autograding",
            "branch": "main",
        }


class TestWebhook:
    def test_create_repo_webhook_defaults_push(self):
        client, http = make_client()
        client.create_repo_webhook(
            "cmput174-f26",
            "lab1-ada",
            target_url="https://classroom.example.edu/v1/grading_run/report",
            secret="hooksecret",
        )
        call = http.calls[0]
        assert call["json"]["type"] == "gitea"
        assert call["json"]["events"] == ["push"]
        assert call["json"]["config"]["secret"] == "hooksecret"
        assert call["json"]["config"]["content_type"] == "json"


class TestTeams:
    def test_create_org_team(self):
        client, http = make_client()
        client.create_org_team("cmput174-f26", "team-rocket")
        call = http.calls[0]
        assert call["url"].endswith("/orgs/cmput174-f26/teams")
        assert call["json"]["name"] == "team-rocket"
        assert call["json"]["permission"] == "write"

    def test_add_team_member(self):
        client, http = make_client()
        client.add_team_member(42, "ada")
        assert http.calls[0]["verb"] == "PUT"
        assert http.calls[0]["url"].endswith("/teams/42/members/ada")

    def test_add_team_repo(self):
        client, http = make_client()
        client.add_team_repo(42, "cmput174-f26", "project-team-rocket")
        assert http.calls[0]["url"].endswith("/teams/42/repos/cmput174-f26/project-team-rocket")


class TestPullRequests:
    def test_create_branch(self):
        client, http = make_client()
        client.create_branch("cmput174-f26", "lab1-ada", "feedback", "main")
        call = http.calls[0]
        assert call["json"] == {
            "new_branch_name": "feedback",
            "old_branch_name": "main",
        }

    def test_create_pull_request(self):
        client, http = make_client()
        client.create_pull_request(
            "cmput174-f26",
            "lab1-ada",
            head="main",
            base="feedback",
            title="Feedback",
            body="Leave feedback here.",
        )
        call = http.calls[0]
        assert call["url"].endswith("/repos/cmput174-f26/lab1-ada/pulls")
        assert call["json"] == {
            "head": "main",
            "base": "feedback",
            "title": "Feedback",
            "body": "Leave feedback here.",
        }


class TestActions:
    def test_set_repo_secret(self):
        client, http = make_client()
        client.set_repo_secret("cmput174-f26", "lab1-ada", "CLASSROOM_REPORT_TOKEN", "s3cr3t")
        call = http.calls[0]
        assert call["verb"] == "PUT"
        assert call["url"].endswith("/repos/cmput174-f26/lab1-ada/actions/secrets/CLASSROOM_REPORT_TOKEN")
        assert call["json"] == {"data": "s3cr3t"}

    def test_dispatch_workflow(self):
        client, http = make_client()
        client.dispatch_workflow("cmput174-f26", "lab1-ada", "autograde.yml", ref="main")
        call = http.calls[0]
        assert call["url"].endswith("/repos/cmput174-f26/lab1-ada/actions/workflows/autograde.yml/dispatches")
        assert call["json"] == {"ref": "main"}
