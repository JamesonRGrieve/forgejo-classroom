# Forgejo Classroom

A GitHub-Classroom-equivalent for [Forgejo](https://forgejo.org), built as
a [Zephyrex](https://github.com/JamesonRGrieve) framework consumer.

Forgejo has **no server-side plugin system** — it is a monolithic Go
binary extensible only through its REST API, webhooks, Forgejo Actions,
and OAuth2 provider. GitHub Classroom itself is likewise a standalone web
app (Rails) that drives GitHub over those same surfaces, not a GitHub
plugin. Forgejo Classroom mirrors that architecture: a **companion
runtime** that sits beside an unmodified Forgejo and drives it.

## Structure

```
server/     Python backend — the `classroom` domain extension on ServerFramework
client/     Next.js frontend — the `classroom` extension on client-framework
```

- **server/** consumes the `zephyrex` PyPI package. The `classroom`
  extension owns the domain (classrooms, rosters, assignments, accepted
  repos, grading runs); the framework auto-generates REST + GraphQL CRUD
  and supplies auth (User/Team/Role). See `server/OBJECT_PLAN.md` for the
  domain rationale and the Forgejo REST/Actions wiring plan.
- **client/** consumes the `zephyrex` npm package and adds a teacher
  dashboard via a single client extension.

## Why the framework fits

| GitHub Classroom concept | Zephyrex primitive |
|--------------------------|--------------------|
| Teachers / TAs / students | framework `User` + `Team` membership + `Role` (RBAC) |
| Classroom (backed by a GitHub org) | `ClassroomModel` → framework `Team` + `forgejo_org` |
| Roster | `RosterEntryModel` (SIS/LMS id ↔ Forgejo user ↔ User) |
| Assignment / template repo | `AssignmentModel` (+ `AssignmentGroupModel`) |
| Accepted repo | `AssignmentRepoModel` |
| Autograding (Actions) | `GradingRunModel` (one Forgejo Actions run) |
| "Log in with GitHub" | Forgejo OAuth2 provider |

## Develop

```bash
# server
cd server
pip install -e "../../server-framework[all]"
pip install -e ".[dev]"
pytest extensions/
python app.py            # http://localhost:2100

# client
cd client
pnpm install
pnpm dev                 # http://localhost:1110
```

## License

AGPL-3.0-or-later.
