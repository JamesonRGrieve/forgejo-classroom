# SPDX-License-Identifier: AGPL-3.0-or-later
"""classroom extension definition.

Depends only on framework core (auth: User, Team, Role). Optionally uses
``acl_rbac`` for per-row visibility (a teacher sees the whole roster and
all grades; a student sees only their own repo and runs). No hard
extension dependency.
"""

from typing import ClassVar

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension
from zephyrex.lib.Dependencies import Dependencies, EXT_Dependency


class ClassroomExtension(AbstractStaticExtension):
    name: ClassVar[str] = "classroom"
    version: ClassVar[str] = "0.1.0"
    description: ClassVar[str] = (
        "GitHub-Classroom-equivalent for Forgejo: classrooms, rosters, "
        "assignments (template repos), accepted repositories, and "
        "autograding runs. Drives Forgejo as a companion runtime."
    )
    dependencies: ClassVar[Dependencies] = Dependencies(
        [
            EXT_Dependency(
                name="acl_rbac",
                friendly_name="ACL / RBAC",
                optional=True,
                reason="Per-row visibility: teachers see the roster, students their own work",
            ),
        ]
    )
