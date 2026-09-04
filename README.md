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
- **client/** consumes the `zephyrex` npm package and adds the teacher +
  student UI via a single client extension.

## Features (GitHub Classroom parity)

- **Classrooms** backed by a Forgejo organization; teacher/TA/student roles
  via framework Teams.
- **Rosters** with CSV import/merge and student↔Forgejo-account linking.
- **Assignments** — individual and group, from a starter **template repo**,
  with deadline, points, visibility, and an invite link.
- **Accept flow** — a student accepts, and their repo is generated from the
  template, access is granted (collaborator or group team), the autograder
  is injected, and a **Feedback** pull request is opened.
- **Autograding** — teacher-defined test cases are injected into each repo
  as a Forgejo Actions workflow + a stdlib grader that runs on every push,
  scores the work, and reports back to a token-authenticated ingest.
- **Gradebook** — per-student/group status and scores, one-click **regrade**,
  **grades CSV** export, and a **batch-clone** script for all submissions.

## GitHub Classroom parity matrix

| GitHub Classroom feature | Status |
|--------------------------|--------|
| Classrooms (org-backed) | ✅ |
| Classroom admins / TAs | ✅ (framework Team roles) |
| Roster create + CSV import + student linking | ✅ |
| Individual assignments | ✅ |
| Group assignments (team per group) | ✅ |
| Starter / template repositories | ✅ |
| Assignment invitation links | ✅ |
| Repo visibility (public/private) | ✅ |
| Deadlines + hard cutoff | ✅ |
| Accept flow → per-student/group repo | ✅ |
| Autograding on push (Actions) | ✅ |
| Autograding presets (I/O, run-command) | ✅ |
| Feedback pull requests | ✅ |
| Submission status + scores dashboard | ✅ |
| Grade export (CSV) | ✅ |
| Batch clone all submissions | ✅ |
| Re-run autograding | ✅ |
| LMS roster sync (LTI) | ⚠️ CSV import is the universal path; LTI not wired |
| "Log in with your git host" identity | ⚠️ student enters username; Forgejo OAuth auto-fill not wired |
| Protected file paths | ⚠️ not implemented |
| Editor / Codespaces integration | N/A — no Forgejo equivalent |

## Configuration (server)

Runtime config comes from the environment — no secrets in the repo:

| Variable | Purpose |
|----------|---------|
| `FORGEJO_BASE_URL` | Forgejo instance base URL (e.g. `https://git.example.edu`) |
| `FORGEJO_TOKEN` | Access token for the classroom service account |
| `CLASSROOM_API_URL` | Public base URL of this app (injected into each repo) |
| `CLASSROOM_REPORT_TOKEN` | Shared bearer token the autograder uses to report |
| `EGRESS_ALLOWED_HOSTS` | Must include the Forgejo host (the framework SSRF guard blocks private hosts otherwise) |

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
node_modules/.bin/next build   # verify build
pnpm dev                       # http://localhost:1110
```

The client consumes the local `client-framework` (and `auth`, `dynamic-form`,
`zod2gql`) via pnpm's **`link:`** protocol — a plain `file:` copy honors the
framework's `files` allowlist, which omits `src/components/*` that the
framework's own code imports.

## License

AGPL-3.0-or-later.
