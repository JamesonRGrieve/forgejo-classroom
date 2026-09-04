# SPDX-License-Identifier: AGPL-3.0-or-later
"""Test configuration for the forgejo-classroom consumer project.

Sets up the extensions path so test imports like
``from zephyrex.extensions.classroom.BLL_Classroom import ...`` resolve to
the local ``./extensions/`` directory.
"""

import os
from pathlib import Path

_project_root = Path(__file__).resolve().parent
_extensions_dir = _project_root / "extensions"

os.environ.setdefault("EXTENSIONS_PATH", str(_extensions_dir))
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("DATABASE_NAME", "test_classroom")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-32-bytes-or-more-aaaaaa")
os.environ.setdefault("SEED_DATA", "true")

import zephyrex.extensions  # noqa: E402

if str(_extensions_dir) not in zephyrex.extensions.__path__:
    zephyrex.extensions.__path__ = [str(_extensions_dir)] + list(zephyrex.extensions.__path__)
