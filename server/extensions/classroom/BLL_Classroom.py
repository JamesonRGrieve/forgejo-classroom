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

Owned tables (6)
----------------
1. ``ClassroomModel``      — tenant root; backed by a Team, linked to a
   Forgejo org, owned by a teacher (User).
2. ``RosterEntryModel``    — identity mapping: an external roster
   identifier (SIS/LMS) ↔ a Forgejo username ↔ a framework User.
3. ``AssignmentModel``     — a template repo + autograding config +
   deadline; individual or group.
4. ``AssignmentGroupModel``— one student team per group (group
   assignments only); backed by a Team.
5. ``AssignmentRepoModel`` — an *accepted* assignment: the per-student or
   per-group repository. ``roster_entry_id`` XOR ``assignment_group_id``.
6. ``GradingRunModel``     — one autograding run per graded push (a
   Forgejo Actions run and its score).

Endpoint XOR on AssignmentRepo
------------------------------
An accepted repo belongs to *either* a single student (individual
assignment → ``roster_entry_id`` set) *or* a group (group assignment →
``assignment_group_id`` set), never both. The exclusivity is documented
here and enforced by a CHECK constraint in the extension's migration; the
manager layer rejects rows that set neither or both.
"""

from datetime import datetime
from typing import ClassVar, List, Literal, Optional, Type

from pydantic import Field

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
from zephyrex.pydantic2.fastapi import RouterMixin
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
    table_comment: ClassVar[str] = (
        "An assignment. template_repo is the starter cloned per "
        "student/group; autograde_workflow names the Forgejo Actions "
        "workflow that scores pushes. is_group toggles individual vs "
        "group provisioning."
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

    class Update(BaseModel):
        name: Optional[str] = None
        description: Optional[str] = None
        template_repo: Optional[str] = None
        deadline: Optional[datetime] = None
        points_possible: Optional[float] = None
        autograde_workflow: Optional[str] = None
        visibility: Optional[AssignmentVisibility] = None
        invite_enabled: Optional[bool] = None

    class Search(ApplicationModel.Search, ClassroomModel.Reference.ID.Search):
        name: Optional[StringSearchModel] = None
        slug: Optional[StringSearchModel] = None
        visibility: Optional[StringSearchModel] = None


class AssignmentManager(AbstractBLLManager, RouterMixin):
    _model = AssignmentModel


AssignmentModel.Manager = AssignmentManager


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
    table_comment: ClassVar[str] = (
        "A student group within a group assignment. team_id is the "
        "framework Team supplying membership; forgejo_team names the "
        "Forgejo team granted access to the shared repo."
    )

    class Create(
        BaseModel,
        AssignmentModel.Reference.ID.Optional,
        TeamModel.Reference.ID.Optional,
    ):
        name: str = Field(...)
        forgejo_team: Optional[str] = None

    class Update(BaseModel):
        name: Optional[str] = None
        forgejo_team: Optional[str] = None

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
        points_possible: Optional[float] = None
        actions_run_id: Optional[str] = None

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


GradingRunModel.Manager = GradingRunManager


# ---------------------------------------------------------------------------
# Public roster
# ---------------------------------------------------------------------------


ALL_MODELS: List[type] = [
    ClassroomModel,
    RosterEntryModel,
    AssignmentModel,
    AssignmentGroupModel,
    AssignmentRepoModel,
    GradingRunModel,
]


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
    "AssignmentGroupModel",
    "AssignmentGroupManager",
    "AssignmentRepoModel",
    "AssignmentRepoManager",
    "GradingRunModel",
    "GradingRunManager",
    "ALL_MODELS",
]
