# Forgejo Classroom — object plan & companion-runtime wiring

Target-state design for the `classroom` extension and the Forgejo
integration it drives. GitHub Classroom is, architecturally, a standalone
Rails app that talks to GitHub over OAuth + REST + webhooks and grades via
GitHub Actions — **not** a GitHub plugin. Forgejo has no server-side
plugin seam either, so this project mirrors that shape: a Zephyrex
consumer app (this server + the sibling client) acts as the companion
runtime and leaves Forgejo unmodified.

## Domain (owned tables)

| Model | Role | Key references |
|-------|------|----------------|
| `ClassroomModel` | Tenant root | `team_id` (org/RBAC), `user_id` (teacher), `forgejo_org` |
| `RosterEntryModel` | Identity mapping | `classroom_id`, `user_id`, `forgejo_username`, `identifier` |
| `AssignmentModel` | Template + grading config | `classroom_id`, `template_repo`, `autograde_workflow` |
| `AssignmentGroupModel` | Student team (group work) | `assignment_id`, `team_id`, `forgejo_team` |
| `AssignmentRepoModel` | Accepted repository | `assignment_id`, `roster_entry_id` XOR `assignment_group_id` |
| `GradingRunModel` | One autograde run | `assignment_repo_id`, `actions_run_id`, `score` |

### Why framework Team/User instead of a members table

A classroom is backed by a framework `Team` (the analog of a Forgejo
organization). Team membership + framework `Role`s already express
teacher / TA / student, so `classroom` owns **no** enrollment or role
table. This is the DRY choice and it lets the optional `acl_rbac`
extension gate per-row visibility (teacher sees all; student sees only
their own repo and runs) without a bespoke visibility column.

### AssignmentRepo endpoint XOR

An accepted repo belongs to exactly one of:

- an individual student → `roster_entry_id` set, `assignment_group_id` NULL;
- a group → `assignment_group_id` set, `roster_entry_id` NULL.

Enforced by a CHECK constraint in the extension migration and by a
manager-layer guard (rejects neither/both), following the endpoint-XOR
pattern used elsewhere in the framework ecosystem.

## Forgejo companion wiring (next increment)

A `forgejo_client.py` module (async `httpx`, bounded timeouts, token from
the environment / OpenBao — never hardcoded) wraps the handful of Forgejo
REST operations the managers call via `hook_bll` hooks. Nothing below
modifies Forgejo; every action uses a documented Forgejo API surface.

| Classroom action | Forgejo REST call | Notes |
|------------------|-------------------|-------|
| Provision accepted repo (individual/group) | `POST /repos/{template_owner}/{template_repo}/generate` | Names it `<slug>-<student|group>` under `forgejo_org` |
| Grant student/group access | `PUT /repos/{owner}/{repo}/collaborators/{user}` or team add | Individual = collaborator; group = Forgejo team |
| Register push webhook | `POST /repos/{owner}/{repo}/hooks` | Points at this app's `/v1/classroom/webhook` ingest |
| Read autograding result | `GET /repos/{owner}/{repo}/actions/runs/{id}` | Populates `GradingRunModel` |
| Identity (accept flow) | Forgejo OAuth2 provider | Links `RosterEntry` → Forgejo user → framework User |

### Autograding

Forgejo Actions is GitHub-Actions-*like* (not 100% compatible). The
autograding workflow (`AssignmentModel.autograde_workflow`, e.g.
`.forgejo/workflows/autograde.yml`) runs on push in each accepted repo,
runs the assignment's tests, and reports a score. The score is ingested
(webhook + `actions/runs` read) into a `GradingRunModel`, and the newest
run's score is mirrored onto `AssignmentRepoModel.latest_score` for
dashboard sorting. The GitHub autograding action is not guaranteed to run
unmodified on Forgejo, so a Forgejo-native grading workflow (a reusable
`workflow_call`) is authored as part of this increment.

### Identity / auth

Student accept flow uses Forgejo as an OAuth2 provider: the student logs
in with Forgejo, which links their `RosterEntry` to their Forgejo
username and their framework `User`. In the target deployment this sits
behind the environment's Authentik SSO with Forgejo's native OIDC — no
edge/forward-proxy auth.

## Deferred (tracked here, not stubbed in code)

The `forgejo_client.py` module and the `hook_bll` provisioning/grading
hooks are the next build increment. They are intentionally **not**
present as unwired stubs — this document is their spec. The current code
is the complete, tested domain layer plus the framework's auto-generated
REST/GraphQL surface.
