# Forgejo Classroom — server

Consumer project built on [ServerFramework](https://github.com/JamesonRGrieve/ServerFramework)
(the `zephyrex` PyPI package). Provides the `classroom` domain extension —
the framework handles all infrastructure.

## Architecture

This is a **consumer project**, not a framework fork, and it is the
server half of a **companion runtime** for Forgejo. Forgejo has no
server-side plugin system, so GitHub-Classroom-style features live here,
beside Forgejo, and drive it over the Forgejo REST API + Forgejo Actions.

The single `classroom` extension owns the domain:

- **ClassroomModel** — tenant root; backed by a framework Team (org +
  RBAC), linked to a Forgejo org, owned by a teacher (User).
- **RosterEntryModel** — SIS/LMS identifier ↔ Forgejo username ↔ User.
- **AssignmentModel** — template repo + autograding config + deadline.
- **AssignmentGroupModel** — one student Team per group assignment.
- **AssignmentRepoModel** — an accepted repo; `roster_entry_id` XOR
  `assignment_group_id`.
- **GradingRunModel** — one autograding run (one Forgejo Actions run).

Membership and roles are **not** reinvented — teachers/TAs/students are
framework Team members with framework Roles.

See `OBJECT_PLAN.md` for the full domain rationale and the Forgejo
companion-runtime wiring plan (REST operation map + autograding).

## Commands

```bash
pip install -e "../../server-framework[all]"   # editable framework (local)
pip install -e ".[dev]"                        # this project + dev deps
python app.py                                  # boot the server on port 2100
pytest extensions/                             # run extension tests
black --check extensions/ app.py conftest.py
```

## How it works

`app.py` calls `zephyrex.run(extensions="classroom", extensions_path="./extensions")`.
The framework:

1. Discovers `BLL_*.py` models in `./extensions/classroom/`.
2. Auto-generates SQLAlchemy tables (dev uses `create_all`).
3. Auto-generates REST CRUD endpoints at `/v1/<resource>`.
4. Auto-generates the GraphQL schema.
5. Provides core auth (User, Team, Role, Session) out of the box.

## License

AGPL-3.0-or-later. SPDX header on every source file.
