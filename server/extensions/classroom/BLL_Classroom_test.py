# SPDX-License-Identifier: AGPL-3.0-or-later
"""Structural tests for the classroom BLL surface.

Covers model↔manager wiring, the Create/Update/Search contract, the
closed enums (visibility, acceptance status, grading status), and the
AssignmentRepo individual-vs-group endpoint model.
"""

import os

import pytest

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "classroom_test")

from zephyrex.extensions.classroom.BLL_Classroom import (
    ALL_MODELS,
    AssignmentGroupManager,
    AssignmentGroupModel,
    AssignmentManager,
    AssignmentModel,
    AssignmentRepoManager,
    AssignmentRepoModel,
    ClassroomManager,
    ClassroomModel,
    GradingRunManager,
    GradingRunModel,
    RosterEntryManager,
    RosterEntryModel,
)


class TestModelManagerWiring:
    """Every owned model must point to its Manager and vice versa."""

    PAIRS = [
        (ClassroomModel, ClassroomManager),
        (RosterEntryModel, RosterEntryManager),
        (AssignmentModel, AssignmentManager),
        (AssignmentGroupModel, AssignmentGroupManager),
        (AssignmentRepoModel, AssignmentRepoManager),
        (GradingRunModel, GradingRunManager),
    ]

    def test_each_model_has_its_manager(self):
        for model, manager in self.PAIRS:
            assert model.Manager is manager, f"{model.__name__} → wrong Manager"
            assert manager._model is model, f"{manager.__name__} → wrong _model"

    def test_all_models_listed(self):
        assert set(ALL_MODELS) == {model for model, _ in self.PAIRS}


class TestCreateUpdateSearchPresent:
    def test_nested_classes_exist(self):
        for model in ALL_MODELS:
            assert hasattr(model, "Create"), f"{model.__name__} missing Create"
            assert hasattr(model, "Update"), f"{model.__name__} missing Update"
            assert hasattr(model, "Search"), f"{model.__name__} missing Search"


class TestClassroomContract:
    def test_classroom_backs_onto_team_and_teacher(self):
        c = ClassroomModel.Create(
            name="CMPUT 174 Fall 2026",
            team_id="team-cmput174",
            user_id="teacher-1",
            forgejo_org="cmput174-f26",
        )
        assert c.name == "CMPUT 174 Fall 2026"
        assert c.team_id == "team-cmput174"
        assert c.user_id == "teacher-1"
        assert c.forgejo_org == "cmput174-f26"

    def test_archived_defaults_false(self):
        c = ClassroomModel(name="X")
        assert c.archived is False


class TestRosterEntryLinking:
    def test_unlinked_entry_has_null_forgejo_and_user(self):
        r = RosterEntryModel.Create(identifier="1234567", display_name="Ada Lovelace")
        assert r.identifier == "1234567"
        assert r.forgejo_username is None

    def test_linked_entry(self):
        from datetime import datetime

        r = RosterEntryModel.Update(
            forgejo_username="ada",
            user_id="user-ada",
            linked_at=datetime(2026, 9, 1, 9, 0),
        )
        assert r.forgejo_username == "ada"
        assert r.user_id == "user-ada"


class TestAssignmentContract:
    def test_individual_assignment_defaults(self):
        a = AssignmentModel(name="Lab 1")
        assert a.is_group is False
        assert a.visibility == "private"
        assert a.invite_enabled is True

    def test_group_assignment_with_template_and_autograding(self):
        a = AssignmentModel.Create(
            name="Project",
            classroom_id="c1",
            slug="project",
            template_repo="cmput174-f26/project-starter",
            is_group=True,
            max_team_size=4,
            points_possible=100.0,
            autograde_workflow=".forgejo/workflows/autograde.yml",
            visibility="public",
        )
        assert a.is_group is True
        assert a.template_repo == "cmput174-f26/project-starter"
        assert a.autograde_workflow == ".forgejo/workflows/autograde.yml"
        assert a.max_team_size == 4

    def test_visibility_rejects_unknown_value(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            AssignmentModel.Create(name="X", visibility="internal")


class TestAssignmentGroupContract:
    def test_group_backed_by_team(self):
        g = AssignmentGroupModel.Create(
            name="Team Rocket",
            assignment_id="a1",
            team_id="team-rocket",
            forgejo_team="team-rocket",
        )
        assert g.assignment_id == "a1"
        assert g.team_id == "team-rocket"
        assert g.forgejo_team == "team-rocket"


class TestAssignmentRepoEndpoints:
    """roster_entry_id (individual) XOR assignment_group_id (group)."""

    def test_individual_repo(self):
        ar = AssignmentRepoModel.Create(
            assignment_id="a1",
            roster_entry_id="r1",
            repo_full_name="cmput174-f26/lab1-ada",
            status="accepted",
        )
        assert ar.roster_entry_id == "r1"
        assert ar.assignment_group_id is None
        assert ar.status == "accepted"

    def test_group_repo(self):
        ar = AssignmentRepoModel.Create(
            assignment_id="a1",
            assignment_group_id="g1",
            repo_full_name="cmput174-f26/project-team-rocket",
            status="accepted",
        )
        assert ar.assignment_group_id == "g1"
        assert ar.roster_entry_id is None

    def test_status_defaults_not_accepted(self):
        ar = AssignmentRepoModel(assignment_id="a1")
        assert ar.status == "not_accepted"

    def test_status_rejects_unknown_value(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            AssignmentRepoModel.Create(assignment_id="a1", status="turned_in")


class TestGradingRunContract:
    def test_run_defaults_queued(self):
        g = GradingRunModel(assignment_repo_id="ar1")
        assert g.status == "queued"

    def test_completed_run_carries_score_and_actions_run(self):
        from datetime import datetime

        g = GradingRunModel.Update(
            status="passed",
            score=87.5,
            points_possible=100.0,
            actions_run_id="42",
            log_url="https://git.example.edu/cmput174-f26/lab1-ada/actions/runs/42",
            completed_at=datetime(2026, 9, 2, 14, 30),
        )
        assert g.status == "passed"
        assert g.score == 87.5
        assert g.actions_run_id == "42"

    def test_status_rejects_unknown_value(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            GradingRunModel.Create(assignment_repo_id="ar1", status="pending")


class TestNoReinventedRbac:
    """classroom reuses framework Team/User for membership + roles; it
    must not ship its own members/roles tables."""

    def test_no_membership_or_role_models(self):
        from zephyrex.extensions.classroom import BLL_Classroom

        for absent in (
            "ClassroomMemberModel",
            "MembershipModel",
            "RoleModel",
            "EnrollmentModel",
        ):
            assert not hasattr(BLL_Classroom, absent)
