# SPDX-License-Identifier: AGPL-3.0-or-later
"""classroom — GitHub-Classroom-equivalent domain for Forgejo.

This extension is the data core of a *companion runtime*: a Zephyrex
consumer app that sits beside a Forgejo instance and drives it over the
Forgejo REST API (repo-from-template, collaborator grants, webhooks) and
Forgejo Actions (autograding). Forgejo itself is left unmodified — it has
no server-side plugin seam — so all classroom state lives here.

Reuse of framework primitives
------------------------------
The framework already ships identity, tenancy, and RBAC:

- ``UserModel`` — teachers, TAs, and students are framework users.
- ``TeamModel`` — a classroom is backed by a framework Team (the analog
  of a Forgejo organization). Team membership + roles supply the
  teacher/TA/student RBAC, so ``classroom`` does **not** reinvent a
  members table. A group assignment's student team is likewise a Team.

Owned tables (7)
----------------
1. ``ClassroomModel``      — tenant root; backed by a Team, linked to a
   Forgejo org, owned by a teacher (User).
2. ``RosterEntryModel``    — identity mapping: an external roster
   identifier (SIS/LMS) ↔ a Forgejo username ↔ a framework User.
3. ``AssignmentModel``     — a template repo + autograding config +
   deadline; individual or group.
4. ``AutogradeTestModel``  — one autograding test case belonging to an
   assignment; rendered into the repo's ``tests.json``.
5. ``AssignmentGroupModel``— one student team per group (group
   assignments only); backed by a Team.
6. ``AssignmentRepoModel`` — an *accepted* assignment: the per-student or
   per-group repository. ``roster_entry_id`` XOR ``assignment_group_id``.
7. ``GradingRunModel``     — one autograding run per graded push (a
   Forgejo Actions run and its score).

Custom routes (companion runtime)
---------------------------------
- ``POST /v1/classroom/{id}/roster/import``  — CSV roster import (teacher).
- ``POST /v1/assignment/{id}/accept``        — provision the repo (student).
- ``POST /v1/assignment/{id}/regrade``       — re-dispatch grading (teacher).
- ``GET  /v1/assignment/{id}/grades.csv``    — gradebook export (teacher).
- ``GET  /v1/assignment/{id}/submissions``   — batch-clone manifest (teacher).
- ``POST /v1/grading_run/report``            — autograder result ingest (CI,
  bearer-token authenticated).

Endpoint XOR on AssignmentRepo
------------------------------
An accepted repo belongs to *either* a single student (individual
assignment → ``roster_entry_id`` set) *or* a group (group assignment →
``assignment_group_id`` set), never both. The exclusivity is documented
here and enforced by a CHECK constraint in the extension's migration; the
manager layer rejects rows that set neither or both.
"""

import base64
import hmac
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Literal, Optional, Type

from fastapi import HTTPException
from pydantic import Field

from zephyrex.extensions.classroom import autograde, reporting
from zephyrex.extensions.classroom.forgejo_client import (
    ForgejoClient,
    ForgejoConfigError,
)
from zephyrex.lib.Environment import env
from zephyrex.lib.Logging import logger
from zephyrex.logic.AbstractLogicManager import (
    AbstractBLLManager,
    ApplicationModel,
    DateSearchModel,
    DescriptionMixinModel,
    ModelMeta,
    NameMixinModel,
    NumericalSearchModel,
    StringSearchModel,
    UpdateMixinModel,
)
from zephyrex.logic.BLL_Auth import TeamModel, UserModel
from zephyrex.pydantic2.fastapi import AuthType, RouterMixin
from zephyrex.pydantic2.registry import BaseModel

# ---------------------------------------------------------------------------
# Closed enums (locked at the Pydantic layer; mirrored by CHECK constraints
# in the migration).
# ---------------------------------------------------------------------------

AssignmentVisibility = Literal["private", "public"]
"""Whether accepted student repositories are private (default) or public."""

AcceptanceStatus = Literal["not_accepted", "accepted", "submitted", "graded"]
"""Lifecycle of an ``AssignmentRepoModel`` row."""

GradingStatus = Literal["queued", "running", "passed", "failed", "error"]
"""Lifecycle of a ``GradingRunModel`` (mirrors a Forgejo Actions run)."""


# ---------------------------------------------------------------------------
# 1. Classroom — tenant root
# ---------------------------------------------------------------------------


class ClassroomModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    TeamModel.Reference.Optional,
    UserModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["ClassroomManager"]] = None
    forgejo_org: Optional[str] = Field(
        None,
        description=(
            "Name of the Forgejo organization backing this classroom. "
            "Accepted-assignment repositories are created under it."
        ),
    )
    archived: Optional[bool] = Field(
        False,
        description="Archived classrooms are read-only in the dashboard.",
    )
    table_comment: ClassVar[str] = (
        "A classroom. team_id supplies membership + teacher/TA/student "
        "RBAC (the analog of a Forgejo org's teams); user_id is the "
        "owning teacher; forgejo_org names the backing Forgejo org."
    )

    class Create(
        BaseModel,
        TeamModel.Reference.ID.Optional,
        UserModel.Reference.ID.Optional,
    ):
        name: str = Field(..., description="Display name of the classroom")
        description: Optional[str] = None
        forgejo_org: Optional[str] = None

    class Update(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None
        forgejo_org: Optional[str] = None
        archived: Optional[bool] = None

    class Search(
        ApplicationModel.Search,
        TeamModel.Reference.ID.Search,
        UserModel.Reference.ID.Search,
    ):
        name: Optional[StringSearchModel] = None
        forgejo_org: Optional[StringSearchModel] = None


class ClassroomManager(AbstractBLLManager, RouterMixin):
    _model = ClassroomModel

    custom_routes: ClassVar[List[Dict[str, Any]]] = [
        {
            "path": "/{classroom_id}/roster/import",
            "method": "post",
            "function": "roster_import_route",
            "auth_type": AuthType.JWT,
            "is_static": False,
            "summary": "Import a roster from CSV",
            "status_code": 200,
        },
    ]

    def roster_import_route(self, classroom_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Teacher-facing: bulk-import/merge roster entries from a CSV."""
        _require_teacher(self, classroom_id)
        csv_text = (body or {}).get("csv", "")
        entries = reporting.parse_roster_csv(csv_text)
        roster = _sibling_root(RosterEntryManager, self)
        created = 0
        updated = 0
        for entry in entries:
            existing = roster.list(classroom_id=classroom_id, identifier=entry["identifier"])
            if existing:
                current = existing[0]
                if entry.get("forgejo_username") and not _val(current, "forgejo_username"):
                    roster.update(
                        _val(current, "id"),
                        forgejo_username=entry["forgejo_username"],
                        display_name=entry.get("display_name"),
                    )
                    updated += 1
                continue
            roster.create(
                classroom_id=classroom_id,
                identifier=entry["identifier"],
                display_name=entry.get("display_name"),
                forgejo_username=entry.get("forgejo_username"),
            )
            created += 1
        return {"imported": created, "updated": updated, "parsed": len(entries)}


ClassroomModel.Manager = ClassroomManager


# ---------------------------------------------------------------------------
# 2. RosterEntry — external roster identity ↔ Forgejo user ↔ framework user
# ---------------------------------------------------------------------------


class RosterEntryModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    ClassroomModel.Reference.Optional,
    UserModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["RosterEntryManager"]] = None
    identifier: Optional[str] = Field(
        None,
        description=(
            "Roster identifier from the school's SIS/LMS (student number, "
            "email, or LTI person id). Stable key the teacher imports."
        ),
    )
    display_name: Optional[str] = Field(None, description="Human-readable student name for the roster UI.")
    forgejo_username: Optional[str] = Field(
        None,
        description=(
            "The student's Forgejo login. NULL until the student links " "their account by accepting an invite."
        ),
    )
    linked_at: Optional[datetime] = Field(
        None,
        description="When the student linked their Forgejo/framework account.",
    )
    table_comment: ClassVar[str] = (
        "Roster row mapping an external roster identifier to a Forgejo "
        "username and a framework User. user_id/forgejo_username stay "
        "NULL until the student accepts and links."
    )

    class Create(
        BaseModel,
        ClassroomModel.Reference.ID.Optional,
        UserModel.Reference.ID.Optional,
    ):
        identifier: str = Field(..., description="SIS/LMS roster identifier")
        display_name: Optional[str] = None
        forgejo_username: Optional[str] = None

    class Update(BaseModel):
        display_name: Optional[str] = None
        forgejo_username: Optional[str] = None
        linked_at: Optional[datetime] = None
        user_id: Optional[str] = None

    class Search(
        ApplicationModel.Search,
        ClassroomModel.Reference.ID.Search,
        UserModel.Reference.ID.Search,
    ):
        identifier: Optional[StringSearchModel] = None
        forgejo_username: Optional[StringSearchModel] = None


class RosterEntryManager(AbstractBLLManager, RouterMixin):
    _model = RosterEntryModel


RosterEntryModel.Manager = RosterEntryManager


# ---------------------------------------------------------------------------
# 3. Assignment — template repo + autograding config + deadline
# ---------------------------------------------------------------------------


class AssignmentModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    DescriptionMixinModel.Optional,
    ClassroomModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["AssignmentManager"]] = None
    slug: Optional[str] = Field(
        None,
        description=(
            "URL-safe invite slug. The accept link is " "/a/<slug>; accepted repos are named <slug>-<student>."
        ),
    )
    template_repo: Optional[str] = Field(
        None,
        description=(
            "Forgejo 'owner/name' of the starter template repository "
            "cloned for each student/group via the repo-generate API."
        ),
    )
    is_group: Optional[bool] = Field(
        False,
        description="True = one shared repo per group; False = one per student.",
    )
    max_team_size: Optional[int] = Field(
        None,
        description="Group assignments only: max members per group (NULL = no cap).",
    )
    deadline: Optional[datetime] = Field(None, description="Submission deadline; NULL = no deadline.")
    points_possible: Optional[float] = Field(None, description="Max autograde score for this assignment.")
    autograde_workflow: Optional[str] = Field(
        None,
        description=(
            "Path/ref of the Forgejo Actions workflow that grades pushes "
            "(e.g. '.forgejo/workflows/autograde.yml'). NULL = no autograding."
        ),
    )
    visibility: Optional[AssignmentVisibility] = Field(
        "private",
        description="Closed enum: private|public. Visibility of accepted repos.",
    )
    invite_enabled: Optional[bool] = Field(True, description="Whether the accept link currently provisions repos.")
    enforce_deadline: Optional[bool] = Field(
        False,
        description="When true, accepting after the deadline is rejected (hard cutoff).",
    )
    table_comment: ClassVar[str] = (
        "An assignment. template_repo is the starter cloned per "
        "student/group; autograde_workflow names the Forgejo Actions "
        "workflow that scores pushes. is_group toggles individual vs "
        "group provisioning. enforce_deadline turns deadline into a cutoff."
    )

    class Create(BaseModel, ClassroomModel.Reference.ID.Optional):
        name: str = Field(...)
        description: Optional[str] = None
        slug: Optional[str] = None
        template_repo: Optional[str] = None
        is_group: Optional[bool] = None
        max_team_size: Optional[int] = None
        deadline: Optional[datetime] = None
        points_possible: Optional[float] = None
        autograde_workflow: Optional[str] = None
        visibility: Optional[AssignmentVisibility] = None
        invite_enabled: Optional[bool] = None
        enforce_deadline: Optional[bool] = None

    class Update(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None
        template_repo: Optional[str] = None
        deadline: Optional[datetime] = None
        points_possible: Optional[float] = None
        autograde_workflow: Optional[str] = None
        visibility: Optional[AssignmentVisibility] = None
        invite_enabled: Optional[bool] = None
        enforce_deadline: Optional[bool] = None

    class Search(ApplicationModel.Search, ClassroomModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None
        slug: Optional[StringSearchModel] = None
        visibility: Optional[StringSearchModel] = None


class AssignmentManager(AbstractBLLManager, RouterMixin):
    _model = AssignmentModel

    custom_routes: ClassVar[List[Dict[str, Any]]] = [
        {
            "path": "/{assignment_id}/accept",
            "method": "post",
            "function": "accept_route",
            "auth_type": AuthType.JWT,
            "is_static": False,
            "summary": "Accept an assignment and provision the student/group repo",
            "status_code": 200,
        },
        {
            "path": "/{assignment_id}/regrade",
            "method": "post",
            "function": "regrade_route",
            "auth_type": AuthType.JWT,
            "is_static": False,
            "summary": "Re-run autograding across every accepted repo",
            "status_code": 200,
        },
        {
            "path": "/{assignment_id}/grades.csv",
            "method": "get",
            "function": "grades_csv_route",
            "auth_type": AuthType.JWT,
            "is_static": False,
            "summary": "Export the assignment gradebook as CSV",
            "status_code": 200,
        },
        {
            "path": "/{assignment_id}/submissions",
            "method": "get",
            "function": "submissions_route",
            "auth_type": AuthType.JWT,
            "is_static": False,
            "summary": "Batch-clone manifest for all accepted repos",
            "status_code": 200,
        },
    ]

    def accept_route(self, assignment_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Student-facing: accept an assignment, provisioning their repo."""
        body = body or {}
        assignment = self.get(id=assignment_id)
        if not assignment:
            raise HTTPException(status_code=404, detail="Assignment not found")
        if not _val(assignment, "invite_enabled", True):
            raise HTTPException(status_code=403, detail="Invitations are closed")
        if _val(assignment, "enforce_deadline") and reporting.deadline_passed(_val(assignment, "deadline")):
            raise HTTPException(status_code=403, detail="The deadline for this assignment has passed")
        classroom = _sibling_root(ClassroomManager, self).get(id=_val(assignment, "classroom_id"))
        org = _val(classroom, "forgejo_org")
        if not org:
            raise HTTPException(
                status_code=409,
                detail="Classroom is not linked to a Forgejo organization",
            )
        forgejo_username = body.get("forgejo_username") or _val(self.requester, "username")
        if not forgejo_username:
            raise HTTPException(status_code=400, detail="A Forgejo username is required to accept")
        roster_entry = _link_roster(self, _val(assignment, "classroom_id"), forgejo_username, body.get("identifier"))
        tests = _assignment_tests(self, assignment_id)
        try:
            if _val(assignment, "is_group"):
                return _provision_group(assignment, org, forgejo_username, body.get("group_name"), self, tests)
            return _provision_individual(assignment, org, forgejo_username, roster_entry, self, tests)
        except ForgejoConfigError as exc:
            raise HTTPException(status_code=503, detail=str(exc))

    def regrade_route(self, assignment_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Teacher-facing: dispatch the autograde workflow on every repo."""
        _require_teacher_for_assignment(self, assignment_id)
        repos = _sibling_root(AssignmentRepoManager, self).list(assignment_id=assignment_id)
        forgejo = _forgejo()
        dispatched = 0
        for repo in repos:
            full = _val(repo, "repo_full_name")
            if not full or "/" not in full:
                continue
            owner, name = full.split("/", 1)
            try:
                forgejo.dispatch_workflow(owner, name, "autograde.yml", ref="main")
                dispatched += 1
            except Exception as exc:  # non-fatal: report and continue the batch
                logger.warning("regrade dispatch failed for %s: %s", full, exc)
        return {"dispatched": dispatched, "total": len(repos)}

    def grades_csv_route(self, assignment_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Teacher-facing: export the gradebook as CSV."""
        _require_teacher_for_assignment(self, assignment_id)
        rows = _grade_rows(self, assignment_id)
        return {
            "filename": f"grades-{assignment_id}.csv",
            "csv": reporting.build_grades_csv(rows),
        }

    def submissions_route(self, assignment_id: str, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Teacher-facing: batch-clone manifest for all accepted repos."""
        _require_teacher_for_assignment(self, assignment_id)
        repos = _sibling_root(AssignmentRepoManager, self).list(assignment_id=assignment_id)
        rows = [{"repo_full_name": _val(r, "repo_full_name")} for r in repos]
        return reporting.build_submissions_manifest(_forgejo_base(), rows)


AssignmentModel.Manager = AssignmentManager


# ---------------------------------------------------------------------------
# 3b. AutogradeTest — a test case belonging to an assignment
# ---------------------------------------------------------------------------


class AutogradeTestModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    AssignmentModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["AutogradeTestManager"]] = None
    setup: Optional[str] = Field(None, description="Shell run once before the test")
    run: Optional[str] = Field(None, description="Shell command whose stdout is graded")
    input: Optional[str] = Field(None, description="stdin fed to the run command")
    expected_output: Optional[str] = Field(None, description="Expected stdout")
    comparison: Optional[autograde.Comparison] = Field("included", description="Closed enum: included|exact|regex")
    timeout: Optional[int] = Field(10, description="Per-test timeout (seconds)")
    points: Optional[float] = Field(1.0, description="Points awarded on pass")
    table_comment: ClassVar[str] = (
        "One autograding test case for an assignment. Rendered into the "
        "repo's .classroom/tests.json on provisioning; the injected grader "
        "runs it and reports the score."
    )

    class Create(BaseModel, AssignmentModel.Reference.ID.Optional):
        name: str = Field(...)
        setup: Optional[str] = None
        run: Optional[str] = None
        input: Optional[str] = None
        expected_output: Optional[str] = None
        comparison: Optional[autograde.Comparison] = None
        timeout: Optional[int] = None
        points: Optional[float] = None

    class Update(BaseModel):
        name: Optional[str] = None
        setup: Optional[str] = None
        run: Optional[str] = None
        input: Optional[str] = None
        expected_output: Optional[str] = None
        comparison: Optional[autograde.Comparison] = None
        timeout: Optional[int] = None
        points: Optional[float] = None

    class Search(ApplicationModel.Search, AssignmentModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None
        comparison: Optional[StringSearchModel] = None


class AutogradeTestManager(AbstractBLLManager, RouterMixin):
    _model = AutogradeTestModel


AutogradeTestModel.Manager = AutogradeTestManager


# ---------------------------------------------------------------------------
# 4. AssignmentGroup — one student team per group (group assignments only)
# ---------------------------------------------------------------------------


class AssignmentGroupModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    NameMixinModel.Optional,
    AssignmentModel.Reference.Optional,
    TeamModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["AssignmentGroupManager"]] = None
    forgejo_team: Optional[str] = Field(
        None,
        description="Slug of the Forgejo team that owns this group's repo.",
    )
    forgejo_team_id: Optional[str] = Field(
        None,
        description="Numeric id of the Forgejo team (needed to add members).",
    )
    table_comment: ClassVar[str] = (
        "A student group within a group assignment. team_id is the "
        "framework Team supplying membership; forgejo_team/forgejo_team_id "
        "identify the Forgejo team granted access to the shared repo."
    )

    class Create(
        BaseModel,
        AssignmentModel.Reference.ID.Optional,
        TeamModel.Reference.ID.Optional,
    ):
        name: str = Field(...)
        forgejo_team: Optional[str] = None
        forgejo_team_id: Optional[str] = None

    class Update(BaseModel):
        name: Optional[str] = None
        forgejo_team: Optional[str] = None
        forgejo_team_id: Optional[str] = None

    class Search(
        ApplicationModel.Search,
        AssignmentModel.Reference.ID.Search,
        TeamModel.Reference.ID.Search,
    ):
        name: Optional[StringSearchModel] = None


class AssignmentGroupManager(AbstractBLLManager, RouterMixin):
    _model = AssignmentGroupModel


AssignmentGroupModel.Manager = AssignmentGroupManager


# ---------------------------------------------------------------------------
# 5. AssignmentRepo — the accepted-assignment repository
# ---------------------------------------------------------------------------


class AssignmentRepoModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    AssignmentModel.Reference.Optional,
    RosterEntryModel.Reference.Optional,
    AssignmentGroupModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["AssignmentRepoManager"]] = None
    # roster_entry_id XOR assignment_group_id — enforced by a CHECK
    # constraint in the migration and by the manager layer. Individual
    # assignments set roster_entry_id; group assignments set
    # assignment_group_id.
    repo_full_name: Optional[str] = Field(
        None,
        description="Forgejo 'owner/name' of the provisioned repository.",
    )
    status: Optional[AcceptanceStatus] = Field(
        "not_accepted",
        description="Closed enum: not_accepted|accepted|submitted|graded.",
    )
    accepted_at: Optional[datetime] = Field(None, description="When the invite was accepted and the repo created.")
    submission_sha: Optional[str] = Field(None, description="Commit SHA of the latest graded submission.")
    latest_score: Optional[float] = Field(None, description="Most recent autograde score (see GradingRun for history).")
    table_comment: ClassVar[str] = (
        "An accepted assignment repository. roster_entry_id (individual) "
        "XOR assignment_group_id (group). latest_score caches the newest "
        "GradingRun.score for dashboard sorting."
    )

    class Create(
        BaseModel,
        AssignmentModel.Reference.ID.Optional,
        RosterEntryModel.Reference.ID.Optional,
        AssignmentGroupModel.Reference.ID.Optional,
    ):
        repo_full_name: Optional[str] = None
        status: Optional[AcceptanceStatus] = None
        accepted_at: Optional[datetime] = None

    class Update(BaseModel):
        repo_full_name: Optional[str] = None
        status: Optional[AcceptanceStatus] = None
        accepted_at: Optional[datetime] = None
        submission_sha: Optional[str] = None
        latest_score: Optional[float] = None

    class Search(
        ApplicationModel.Search,
        AssignmentModel.Reference.ID.Search,
        RosterEntryModel.Reference.ID.Search,
        AssignmentGroupModel.Reference.ID.Search,
    ):
        repo_full_name: Optional[StringSearchModel] = None
        status: Optional[StringSearchModel] = None
        latest_score: Optional[NumericalSearchModel] = None


class AssignmentRepoManager(AbstractBLLManager, RouterMixin):
    _model = AssignmentRepoModel


AssignmentRepoModel.Manager = AssignmentRepoManager


# ---------------------------------------------------------------------------
# 6. GradingRun — one autograding run per graded push
# ---------------------------------------------------------------------------


class GradingRunModel(
    ApplicationModel.Optional,
    UpdateMixinModel.Optional,
    AssignmentRepoModel.Reference.Optional,
    metaclass=ModelMeta,
):
    Manager: ClassVar[Type["GradingRunManager"]] = None
    commit_sha: Optional[str] = Field(None, description="The pushed commit this run graded.")
    status: Optional[GradingStatus] = Field(
        "queued",
        description="Closed enum: queued|running|passed|failed|error.",
    )
    score: Optional[float] = Field(None, description="Points earned by this run.")
    points_possible: Optional[float] = Field(None, description="Max points at the time of the run (snapshot).")
    actions_run_id: Optional[str] = Field(None, description="Forgejo Actions run id backing this grading run.")
    log_url: Optional[str] = Field(None, description="URL to the Actions run log for teacher review.")
    started_at: Optional[datetime] = Field(None)
    completed_at: Optional[datetime] = Field(None)
    table_comment: ClassVar[str] = (
        "A single autograding run (one Forgejo Actions run) against an "
        "AssignmentRepo commit. The newest run's score is mirrored onto "
        "AssignmentRepo.latest_score."
    )

    class Create(BaseModel, AssignmentRepoModel.Reference.ID.Optional):
        commit_sha: Optional[str] = None
        status: Optional[GradingStatus] = None
        score: Optional[float] = None
        points_possible: Optional[float] = None
        actions_run_id: Optional[str] = None
        log_url: Optional[str] = None

    class Update(BaseModel):
        status: Optional[GradingStatus] = None
        score: Optional[float] = None
        points_possible: Optional[float] = None
        actions_run_id: Optional[str] = None
        log_url: Optional[str] = None
        started_at: Optional[datetime] = None
        completed_at: Optional[datetime] = None

    class Search(
        ApplicationModel.Search,
        AssignmentRepoModel.Reference.ID.Search,
    ):
        commit_sha: Optional[StringSearchModel] = None
        status: Optional[StringSearchModel] = None
        score: Optional[NumericalSearchModel] = None
        started_at: Optional[DateSearchModel] = None


class GradingRunManager(AbstractBLLManager, RouterMixin):
    _model = GradingRunModel

    # Pin the route base so the injected grader's callback URL
    # (/v1/grading_run/report) is stable regardless of name derivation.
    prefix: ClassVar[str] = "/v1/grading_run"

    custom_routes: ClassVar[List[Dict[str, Any]]] = [
        {
            "path": "/report",
            "method": "post",
            "function": "report_route",
            "is_static": True,
            "summary": "Autograder result ingest (token-authenticated)",
            "status_code": 200,
        },
    ]

    @staticmethod
    def report_route(
        model_registry: Any = None,
        authorization: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """CI-facing: ingest an autograding result.

        Authenticated by a shared bearer token (``CLASSROOM_REPORT_TOKEN``)
        injected into each repo as an Actions secret — not by JWT, since
        the caller is a CI runner. Constant-time token comparison.
        """
        expected = _report_token()
        provided = ""
        if authorization and authorization.lower().startswith("bearer "):
            provided = authorization[7:]
        if not expected or not provided or not hmac.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid or missing report token")
        body = body or {}
        repo_full = body.get("repo_full_name")
        if not repo_full:
            raise HTTPException(status_code=400, detail="repo_full_name is required")
        root = _root_id()
        repos = AssignmentRepoManager(requester_id=root, model_registry=model_registry).list(repo_full_name=repo_full)
        if not repos:
            raise HTTPException(status_code=404, detail="Unknown repository")
        assignment_repo = repos[0]
        score = body.get("score")
        status = body.get("status", "error")
        run = GradingRunManager(requester_id=root, model_registry=model_registry).create(
            assignment_repo_id=_val(assignment_repo, "id"),
            commit_sha=body.get("commit_sha"),
            status=status,
            score=score,
            points_possible=body.get("points_possible"),
            actions_run_id=(str(body["actions_run_id"]) if body.get("actions_run_id") else None),
            log_url=body.get("log_url"),
        )
        AssignmentRepoManager(requester_id=root, model_registry=model_registry).update(
            _val(assignment_repo, "id"),
            latest_score=score,
            submission_sha=body.get("commit_sha"),
            status="graded",
        )
        return {
            "grading_run_id": _val(run, "id"),
            "status": status,
            "score": score,
        }


GradingRunModel.Manager = GradingRunManager


# ---------------------------------------------------------------------------
# Public roster
# ---------------------------------------------------------------------------


ALL_MODELS: List[type] = [
    ClassroomModel,
    RosterEntryModel,
    AssignmentModel,
    AutogradeTestModel,
    AssignmentGroupModel,
    AssignmentRepoModel,
    GradingRunModel,
]


# ---------------------------------------------------------------------------
# Companion-runtime helpers (config, identity, provisioning)
# ---------------------------------------------------------------------------
#
# These orchestrate the tested pure engines (forgejo_client, autograde,
# reporting). Forgejo-touching writes run as the system (ROOT) identity
# because they are triggered by an authenticated student's accept but must
# create rows the student cannot own directly.

_TEST_FIELDS = (
    "name",
    "setup",
    "run",
    "input",
    "expected_output",
    "comparison",
    "timeout",
    "points",
)


def _val(obj: Any, name: str, default: Any = None) -> Any:
    """Read an attribute from a model object or a dict uniformly."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _root_id() -> str:
    from zephyrex.database.StaticPermissions import ROOT_ID

    return ROOT_ID


def _is_root(user_id: Optional[str]) -> bool:
    from zephyrex.database.StaticPermissions import is_root_id

    return bool(user_id) and is_root_id(user_id)


def _sibling(manager_class: Type, manager: AbstractBLLManager) -> Any:
    return manager_class(
        requester_id=_val(manager.requester, "id"),
        model_registry=manager.model_registry,
    )


def _sibling_root(manager_class: Type, manager: AbstractBLLManager) -> Any:
    return manager_class(requester_id=_root_id(), model_registry=manager.model_registry)


def _forgejo() -> ForgejoClient:
    return ForgejoClient()


def _forgejo_base() -> str:
    return (env("FORGEJO_BASE_URL") or "").rstrip("/")


def _report_token() -> str:
    return env("CLASSROOM_REPORT_TOKEN")


def _api_base() -> str:
    return env("CLASSROOM_API_URL")


def _require_teacher(manager: AbstractBLLManager, classroom_id: str) -> None:
    """Authorize the requester as the classroom's owning teacher (or root)."""
    requester_id = _val(manager.requester, "id")
    if _is_root(requester_id):
        return
    classroom = _sibling_root(ClassroomManager, manager).get(id=classroom_id)
    if not classroom or _val(classroom, "user_id") != requester_id:
        raise HTTPException(status_code=403, detail="Teacher access required")


def _require_teacher_for_assignment(manager: AbstractBLLManager, assignment_id: str) -> None:
    assignment = manager.get(id=assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    _require_teacher(manager, _val(assignment, "classroom_id"))


def _assignment_tests(manager: AbstractBLLManager, assignment_id: str) -> List[Dict[str, Any]]:
    rows = _sibling_root(AutogradeTestManager, manager).list(assignment_id=assignment_id)
    return [{field: _val(row, field) for field in _TEST_FIELDS} for row in rows]


def _link_roster(
    manager: AbstractBLLManager,
    classroom_id: str,
    forgejo_username: str,
    identifier: Optional[str],
) -> Any:
    """Find or create the roster entry for an accepting student and link it."""
    roster = _sibling_root(RosterEntryManager, manager)
    user_id = _val(manager.requester, "id")
    by_username = roster.list(classroom_id=classroom_id, forgejo_username=forgejo_username)
    if by_username:
        return by_username[0]
    if identifier:
        by_identifier = roster.list(classroom_id=classroom_id, identifier=identifier)
        if by_identifier:
            entry = by_identifier[0]
            roster.update(
                _val(entry, "id"),
                forgejo_username=forgejo_username,
                user_id=user_id,
                linked_at=_now(),
            )
            return entry
    return roster.create(
        classroom_id=classroom_id,
        identifier=identifier or forgejo_username,
        forgejo_username=forgejo_username,
        user_id=user_id,
        linked_at=_now(),
    )


def _inject_autograde(forgejo: ForgejoClient, org: str, repo: str, tests: List[Dict[str, Any]]) -> None:
    """Commit the workflow, tests.json, and grader into a fresh repo."""
    if not tests:
        return
    forgejo.put_file(
        org,
        repo,
        autograde.WORKFLOW_PATH,
        _b64(autograde.generate_workflow_yaml()),
        "Add autograding workflow",
        branch="main",
    )
    forgejo.put_file(
        org,
        repo,
        autograde.TESTS_PATH,
        _b64(autograde.generate_tests_json(tests)),
        "Add autograding tests",
        branch="main",
    )
    forgejo.put_file(
        org,
        repo,
        autograde.GRADER_PATH,
        _b64(autograde.generate_grader_script()),
        "Add autograder",
        branch="main",
    )


def _finalize_repo(forgejo: ForgejoClient, org: str, repo: str) -> None:
    """Inject reporting secrets and open the feedback PR (best-effort)."""
    token = _report_token()
    api = _api_base()
    try:
        if token:
            forgejo.set_repo_secret(org, repo, "CLASSROOM_REPORT_TOKEN", token)
        if api:
            forgejo.set_repo_secret(org, repo, "CLASSROOM_API_URL", api)
    except Exception as exc:  # non-fatal: autograding can be re-enabled later
        logger.warning("failed to set reporting secrets on %s/%s: %s", org, repo, exc)
    try:
        forgejo.create_branch(org, repo, "feedback", "main")
        forgejo.create_pull_request(
            org,
            repo,
            head="main",
            base="feedback",
            title="Feedback",
            body="Leave inline feedback for the student on this pull request.",
        )
    except Exception as exc:  # feedback PR is optional
        logger.info("feedback PR skipped for %s/%s: %s", org, repo, exc)


def _template_parts(assignment: Any) -> tuple:
    template = _val(assignment, "template_repo")
    if not template or "/" not in template:
        raise HTTPException(status_code=422, detail="Assignment has no valid template_repo (owner/name)")
    owner, repo = template.split("/", 1)
    return owner, repo


def _provision_individual(
    assignment: Any,
    org: str,
    forgejo_username: str,
    roster_entry: Any,
    manager: AbstractBLLManager,
    tests: List[Dict[str, Any]],
) -> Dict[str, Any]:
    slug = _val(assignment, "slug") or reporting.slugify(_val(assignment, "name") or "assignment")
    repo_name = reporting.repo_name_for(slug, forgejo_username)
    repo_full = f"{org}/{repo_name}"
    repos = _sibling_root(AssignmentRepoManager, manager)
    existing = repos.list(assignment_id=_val(assignment, "id"), roster_entry_id=_val(roster_entry, "id"))
    if existing:
        return {
            "repo_full_name": _val(existing[0], "repo_full_name"),
            "html_url": f"{_forgejo_base()}/{_val(existing[0], 'repo_full_name')}",
            "assignment_repo_id": _val(existing[0], "id"),
            "status": "already_accepted",
        }
    forgejo = _forgejo()
    t_owner, t_repo = _template_parts(assignment)
    private = _val(assignment, "visibility", "private") != "public"
    forgejo.generate_repo_from_template(
        t_owner,
        t_repo,
        owner=org,
        name=repo_name,
        private=private,
        description=f"{_val(assignment, 'name')} — {forgejo_username}",
    )
    forgejo.add_collaborator(org, repo_name, forgejo_username, permission="write")
    _inject_autograde(forgejo, org, repo_name, tests)
    _finalize_repo(forgejo, org, repo_name)
    created = repos.create(
        assignment_id=_val(assignment, "id"),
        roster_entry_id=_val(roster_entry, "id"),
        repo_full_name=repo_full,
        status="accepted",
        accepted_at=_now(),
    )
    return {
        "repo_full_name": repo_full,
        "html_url": f"{_forgejo_base()}/{repo_full}",
        "assignment_repo_id": _val(created, "id"),
        "status": "accepted",
    }


def _provision_group(
    assignment: Any,
    org: str,
    forgejo_username: str,
    group_name: Optional[str],
    manager: AbstractBLLManager,
    tests: List[Dict[str, Any]],
) -> Dict[str, Any]:
    slug = _val(assignment, "slug") or reporting.slugify(_val(assignment, "name") or "assignment")
    group_name = group_name or f"{forgejo_username}-group"
    groups = _sibling_root(AssignmentGroupManager, manager)
    repos = _sibling_root(AssignmentRepoManager, manager)
    forgejo = _forgejo()
    existing_groups = groups.list(assignment_id=_val(assignment, "id"), name=group_name)
    if existing_groups:
        group = existing_groups[0]
        team_id = _val(group, "forgejo_team_id")
        if team_id:
            try:
                forgejo.add_team_member(int(team_id), forgejo_username)
            except Exception as exc:
                logger.warning("failed to add %s to team %s: %s", forgejo_username, team_id, exc)
        group_repos = repos.list(assignment_group_id=_val(group, "id"))
        repo_full = _val(group_repos[0], "repo_full_name") if group_repos else None
        return {
            "repo_full_name": repo_full,
            "html_url": f"{_forgejo_base()}/{repo_full}" if repo_full else None,
            "status": "joined",
        }
    team = forgejo.create_org_team(org, f"{slug}-{reporting.slugify(group_name)}")
    team_id = _val(team, "id")
    if team_id:
        forgejo.add_team_member(int(team_id), forgejo_username)
    repo_name = reporting.repo_name_for(slug, group_name)
    repo_full = f"{org}/{repo_name}"
    t_owner, t_repo = _template_parts(assignment)
    private = _val(assignment, "visibility", "private") != "public"
    forgejo.generate_repo_from_template(
        t_owner,
        t_repo,
        owner=org,
        name=repo_name,
        private=private,
        description=f"{_val(assignment, 'name')} — {group_name}",
    )
    if team_id:
        forgejo.add_team_repo(int(team_id), org, repo_name)
    _inject_autograde(forgejo, org, repo_name, tests)
    _finalize_repo(forgejo, org, repo_name)
    group = groups.create(
        assignment_id=_val(assignment, "id"),
        name=group_name,
        forgejo_team=_val(team, "name"),
        forgejo_team_id=str(team_id) if team_id else None,
    )
    created = repos.create(
        assignment_id=_val(assignment, "id"),
        assignment_group_id=_val(group, "id"),
        repo_full_name=repo_full,
        status="accepted",
        accepted_at=_now(),
    )
    return {
        "repo_full_name": repo_full,
        "html_url": f"{_forgejo_base()}/{repo_full}",
        "assignment_repo_id": _val(created, "id"),
        "status": "accepted",
    }


def _grade_rows(manager: AbstractBLLManager, assignment_id: str) -> List[Dict[str, Any]]:
    assignment = manager.get(id=assignment_id)
    points_possible = _val(assignment, "points_possible")
    repos = _sibling_root(AssignmentRepoManager, manager).list(assignment_id=assignment_id)
    roster = _sibling_root(RosterEntryManager, manager)
    rows: List[Dict[str, Any]] = []
    for repo in repos:
        entry_id = _val(repo, "roster_entry_id")
        entry = roster.get(id=entry_id) if entry_id else None
        rows.append(
            {
                "identifier": _val(entry, "identifier", ""),
                "display_name": _val(entry, "display_name", ""),
                "forgejo_username": _val(entry, "forgejo_username", ""),
                "repo_full_name": _val(repo, "repo_full_name", ""),
                "status": _val(repo, "status", ""),
                "score": _val(repo, "latest_score", ""),
                "points_possible": points_possible if points_possible is not None else "",
                "submission_sha": _val(repo, "submission_sha", ""),
            }
        )
    return rows


__all__ = [
    "AssignmentVisibility",
    "AcceptanceStatus",
    "GradingStatus",
    "ClassroomModel",
    "ClassroomManager",
    "RosterEntryModel",
    "RosterEntryManager",
    "AssignmentModel",
    "AssignmentManager",
    "AutogradeTestModel",
    "AutogradeTestManager",
    "AssignmentGroupModel",
    "AssignmentGroupManager",
    "AssignmentRepoModel",
    "AssignmentRepoManager",
    "GradingRunModel",
    "GradingRunManager",
    "ALL_MODELS",
]
