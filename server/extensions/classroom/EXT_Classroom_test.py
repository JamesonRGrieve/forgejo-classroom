# SPDX-License-Identifier: AGPL-3.0-or-later
"""Extension-level tests for classroom."""

import os
from pathlib import Path

os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("PYTEST_CURRENT_TEST", "classroom_ext_test")

from zephyrex.extensions.Manifest import load_manifest
from zephyrex.extensions.classroom.BLL_Classroom import ALL_MODELS
from zephyrex.extensions.classroom.EXT_Classroom import ClassroomExtension

MANIFEST = Path(__file__).with_name("manifest.toml")


class TestExtensionMetadata:
    def test_name_and_description(self):
        assert ClassroomExtension.name == "classroom"
        assert "Forgejo" in ClassroomExtension.description

    def test_acl_rbac_is_the_only_dependency_and_optional(self):
        # classroom builds only on framework core (auth). acl_rbac is an
        # optional runtime enhancement for per-row visibility.
        declared = {(d.name, d.optional) for d in ClassroomExtension.dependencies.ext}
        assert declared == {("acl_rbac", True)}

    def test_discovered_models_are_the_roster(self):
        assert ClassroomExtension.models == set(ALL_MODELS)
        assert len(ALL_MODELS) == 7  # bump when adding owned tables.


class TestManifest:
    # A manifest the framework's schema rejects made GET /source fail with
    # a 500 on zephyrex 0.0.1 while every other test passed.
    def test_validates_against_the_framework_schema(self):
        manifest = load_manifest(MANIFEST)
        assert manifest.entry_module == "EXT_Classroom"
        assert manifest.repository == "https://github.com/JamesonRGrieve/forgejo-classroom"

    def test_mirrors_the_extension_class(self):
        manifest = load_manifest(MANIFEST)
        assert manifest.name == ClassroomExtension.name
        assert manifest.version == ClassroomExtension.version
        assert manifest.description == ClassroomExtension.description
        assert {(d.name, d.optional) for d in manifest.extension_dependencies} == {
            (d.name, d.optional) for d in ClassroomExtension.dependencies.ext
        }
