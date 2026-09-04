# SPDX-License-Identifier: AGPL-3.0-or-later
"""forgejo-classroom — a consumer app built on ServerFramework.

Provides the ``classroom`` extension (GitHub-Classroom-equivalent domain
for Forgejo). All infrastructure (auth, DB, REST, GraphQL, migrations)
comes from the framework; this project provides only the domain models
and, in later increments, the Forgejo companion-runtime wiring.

    python app.py              # boot with uvicorn
    python -c "from app import create; create()"  # programmatic
"""

import os

os.environ.setdefault("APP_NAME", "Forgejo Classroom")
os.environ.setdefault("DATABASE_TYPE", "sqlite")
os.environ.setdefault("DATABASE_NAME", "forgejo_classroom")
os.environ.setdefault("SEED_DATA", "true")
os.environ.setdefault("JWT_SECRET", "dev-only-change-in-production-32chars!")

from zephyrex import run

EXTENSIONS = "classroom"

if __name__ == "__main__":
    run(
        extensions=EXTENSIONS,
        extensions_path="./extensions",
        port=2100,
    )


def create():
    """Return a FastAPI app instance for testing or ASGI mounting."""
    from zephyrex import instance, set_extensions_root

    set_extensions_root("./extensions")
    return instance(extensions=EXTENSIONS)
