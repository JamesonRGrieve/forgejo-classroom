# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extension-level tests for classroom."""

import os

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "classroom_ext_test")

from zephyrex.extensions.classroom.BLL_Classroom import ALL_MODELS
from zephyrex.extensions.classroom.EXT_Classroom import ClassroomExtension


class TestExtensionMetadata:
    def test_name_and_description(self):
        assert ClassroomExtension.name == "classroom"
        assert "Forgejo" in ClassroomExtension.description

    def test_no_hard_dependencies(self):
        # classroom builds only on framework core (auth). acl_rbac is an
        # optional runtime enhancement declared in manifest.toml, not a
        # hard import dependency.
        assert ClassroomExtension.extension_dependencies == []

    def test_models_returns_full_roster(self):
        models = ClassroomExtension.models()
        assert set(models) == set(ALL_MODELS)
        assert len(models) == 7  # bump when adding owned tables.
