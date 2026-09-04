# SPDX-License-Identifier: AGPL-3.0-or-later
"""forgejo_client — thin, typed wrapper over the Forgejo (Gitea) REST API.

This is the companion runtime's outbound edge: every mutation the
classroom managers perform on Forgejo goes through here. It builds on the
framework's ``ProviderHTTPClientSync`` (SSRF guard, timeout, error
classification) so classroom code never touches ``httpx`` directly.

Config comes from the environment (never hardcoded):

- ``FORGEJO_BASE_URL`` — e.g. ``https://git.example.edu``
- ``FORGEJO_TOKEN``    — an access token for a classroom service account

Because Forgejo is typically on a private network, its host must be added
to ``EGRESS_ALLOWED_HOSTS`` (the framework's SSRF allowlist) in the
deployment environment, or the outbound call is refused.

The HTTP client is injectable (``http=``) so request construction is unit
tested without a live Forgejo: any object exposing ``get/post/put/patch/
delete(url, *, json=, params=, headers=)`` and returning parsed JSON works.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol

from zephyrex.lib.Environment import env
from zephyrex.lib.ProviderHTTPClient import ProviderHTTPClientSync

# Default write permission granted to a student on their own repository.
_DEFAULT_COLLAB_PERMISSION = "write"
# Forgejo webhook type discriminator for JSON-delivery hooks.
_WEBHOOK_TYPE = "gitea"


class HTTPLike(Protocol):
    """Structural type for the injectable HTTP client."""

    def get(self, url: str, **kw: Any) -> Any: ...

    def post(self, url: str, **kw: Any) -> Any: ...

    def put(self, url: str, **kw: Any) -> Any: ...

    def patch(self, url: str, **kw: Any) -> Any: ...

    def delete(self, url: str, **kw: Any) -> Any: ...


class ForgejoConfigError(RuntimeError):
    """Raised when the Forgejo base URL or token is not configured."""


class ForgejoClient:
    """Synchronous Forgejo REST client used by the classroom BLL."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        token: Optional[str] = None,
        http: Optional[HTTPLike] = None,
    ) -> None:
        self.base_url = (base_url or env("FORGEJO_BASE_URL")).rstrip("/")
        self._token = token or env("FORGEJO_TOKEN")
        self._http: HTTPLike = http or ProviderHTTPClientSync(provider_name="forgejo")

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self._token)

    @property
    def api(self) -> str:
        return f"{self.base_url}/api/v1"

    def _require_config(self) -> None:
        if not self.configured:
            raise ForgejoConfigError(
                "Forgejo is not configured: set FORGEJO_BASE_URL and FORGEJO_TOKEN "
                "(and add the host to EGRESS_ALLOWED_HOSTS)."
            )

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"token {self._token}"
        return headers

    # --- Repositories --------------------------------------------------------

    def generate_repo_from_template(
        self,
        template_owner: str,
        template_repo: str,
        owner: str,
        name: str,
        private: bool = True,
        description: str = "",
    ) -> Dict[str, Any]:
        """POST /repos/{template_owner}/{template_repo}/generate."""
        self._require_config()
        url = f"{self.api}/repos/{template_owner}/{template_repo}/generate"
        payload = {
            "owner": owner,
            "name": name,
            "private": private,
            "description": description,
            "git_content": True,
        }
        return self._http.post(url, json=payload, headers=self._headers())

    def get_repo(self, owner: str, repo: str) -> Dict[str, Any]:
        self._require_config()
        return self._http.get(f"{self.api}/repos/{owner}/{repo}", headers=self._headers())

    def list_org_repos(self, org: str) -> List[Dict[str, Any]]:
        self._require_config()
        return self._http.get(f"{self.api}/orgs/{org}/repos", headers=self._headers())

    def add_collaborator(
        self,
        owner: str,
        repo: str,
        username: str,
        permission: str = _DEFAULT_COLLAB_PERMISSION,
    ) -> Any:
        """PUT /repos/{owner}/{repo}/collaborators/{username}."""
        self._require_config()
        url = f"{self.api}/repos/{owner}/{repo}/collaborators/{username}"
        return self._http.put(url, json={"permission": permission}, headers=self._headers())

    # --- File contents (workflow / grader injection) -------------------------

    def put_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content_b64: str,
        message: str,
        branch: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /repos/{owner}/{repo}/contents/{path} — create a file.

        ``content_b64`` must already be base64-encoded (Forgejo's contract).
        """
        self._require_config()
        url = f"{self.api}/repos/{owner}/{repo}/contents/{path}"
        payload: Dict[str, Any] = {"content": content_b64, "message": message}
        if branch:
            payload["branch"] = branch
        return self._http.post(url, json=payload, headers=self._headers())

    # --- Webhooks ------------------------------------------------------------

    def create_repo_webhook(
        self,
        owner: str,
        repo: str,
        target_url: str,
        secret: str,
        events: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """POST /repos/{owner}/{repo}/hooks."""
        self._require_config()
        url = f"{self.api}/repos/{owner}/{repo}/hooks"
        payload = {
            "type": _WEBHOOK_TYPE,
            "active": True,
            "events": events or ["push"],
            "config": {
                "url": target_url,
                "content_type": "json",
                "secret": secret,
            },
        }
        return self._http.post(url, json=payload, headers=self._headers())

    # --- Teams (group assignments) -------------------------------------------

    def create_org_team(self, org: str, name: str, permission: str = _DEFAULT_COLLAB_PERMISSION) -> Dict[str, Any]:
        """POST /orgs/{org}/teams."""
        self._require_config()
        url = f"{self.api}/orgs/{org}/teams"
        payload = {
            "name": name,
            "permission": permission,
            "units": ["repo.code", "repo.issues", "repo.pulls"],
            "includes_all_repositories": False,
        }
        return self._http.post(url, json=payload, headers=self._headers())

    def add_team_member(self, team_id: int, username: str) -> Any:
        """PUT /teams/{team_id}/members/{username}."""
        self._require_config()
        url = f"{self.api}/teams/{team_id}/members/{username}"
        return self._http.put(url, headers=self._headers())

    def add_team_repo(self, team_id: int, org: str, repo: str) -> Any:
        """PUT /teams/{team_id}/repos/{org}/{repo}."""
        self._require_config()
        url = f"{self.api}/teams/{team_id}/repos/{org}/{repo}"
        return self._http.put(url, headers=self._headers())

    # --- Pull requests (feedback PR) -----------------------------------------

    def create_branch(self, owner: str, repo: str, new_branch: str, old_branch: str) -> Dict[str, Any]:
        """POST /repos/{owner}/{repo}/branches."""
        self._require_config()
        url = f"{self.api}/repos/{owner}/{repo}/branches"
        payload = {"new_branch_name": new_branch, "old_branch_name": old_branch}
        return self._http.post(url, json=payload, headers=self._headers())

    def create_pull_request(
        self,
        owner: str,
        repo: str,
        head: str,
        base: str,
        title: str,
        body: str = "",
    ) -> Dict[str, Any]:
        """POST /repos/{owner}/{repo}/pulls."""
        self._require_config()
        url = f"{self.api}/repos/{owner}/{repo}/pulls"
        payload = {"head": head, "base": base, "title": title, "body": body}
        return self._http.post(url, json=payload, headers=self._headers())

    # --- Actions (autograding) ----------------------------------------------

    def set_repo_secret(self, owner: str, repo: str, name: str, value: str) -> Any:
        """PUT /repos/{owner}/{repo}/actions/secrets/{name}.

        Used to inject the classroom API URL + report token into each
        accepted repo so its autograde workflow can report results back.
        """
        self._require_config()
        url = f"{self.api}/repos/{owner}/{repo}/actions/secrets/{name}"
        return self._http.put(url, json={"data": value}, headers=self._headers())

    def dispatch_workflow(self, owner: str, repo: str, workflow: str, ref: str = "main") -> Any:
        """POST /repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches."""
        self._require_config()
        url = f"{self.api}/repos/{owner}/{repo}/actions/workflows/{workflow}/dispatches"
        return self._http.post(url, json={"ref": ref}, headers=self._headers())

    # --- Users ---------------------------------------------------------------

    def get_user(self, username: str) -> Dict[str, Any]:
        self._require_config()
        return self._http.get(f"{self.api}/users/{username}", headers=self._headers())


__all__ = ["ForgejoClient", "ForgejoConfigError", "HTTPLike"]
