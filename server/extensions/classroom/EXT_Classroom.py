# SPDX-License-Identifier: AGPL-3.0-or-later
"""classroom extension definition.

Depends only on framework core (auth: User, Team, Role). Optionally uses
``acl_rbac`` for per-row visibility (a teacher sees the whole roster and
all grades; a student sees only their own repo and runs). No hard
extension dependency.
"""

from typing import ClassVar, List, Type

from zephyrex.extensions.AbstractExtensionProvider import AbstractStaticExtension


class ClassroomExtension(AbstractStaticExtension):
    name: ClassVar[str] = "classroom"
    description: ClassVar[str] = (
        "GitHub-Classroom-equivalent for Forgejo: classrooms, rosters, "
        "assignments (template repos), accepted repositories, and "
        "autograding runs. Drives Forgejo as a companion runtime."
    )
    extension_dependencies: ClassVar[List[str]] = []

    @classmethod
    def models(cls) -> List[Type]:
        from zephyrex.extensions.classroom.BLL_Classroom import ALL_MODELS

        return list(ALL_MODELS)
