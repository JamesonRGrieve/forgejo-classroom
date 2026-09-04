# Forgejo Classroom

GitHub Classroom for a [Forgejo](https://forgejo.org) server you run yourself.

[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0--or--later-blue.svg)](./LICENSE)
[![status: alpha](https://img.shields.io/badge/status-alpha-orange.svg)](#project-status)

Teachers hand out coding assignments, students accept them, and every push gets
graded automatically. It works like GitHub Classroom, except the git server is
your own Forgejo instance and the student data never leaves it.

Forgejo has no plugin system for the server itself. You extend it from the
outside, through its REST API, webhooks, Forgejo Actions, and OAuth2 provider.
GitHub Classroom works the same way: it is a separate web app that drives GitHub
through those APIs, not something running inside GitHub. Forgejo Classroom takes
the same shape. It runs next to Forgejo, drives it through the API, and leaves
Forgejo itself untouched.

## Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Install and run](#install-and-run)
- [Configuration](#configuration)
- [Usage](#usage)
- [Autograding](#autograding)
- [Parity with GitHub Classroom](#parity-with-github-classroom)
- [Project status](#project-status)
- [Contributing](#contributing)
- [License](#license)
- [Built on](#built-on)

## How it works

The project is two apps built on the [Zephyrex](https://github.com/JamesonRGrieve)
framework.

```
server/     Python backend, the `classroom` extension on ServerFramework
client/     Next.js frontend, the `classroom` extension on client-framework
```

The server owns the domain: classrooms, rosters, assignments, accepted
repositories, and grading runs. The framework generates the REST and GraphQL
API for those models and provides accounts, teams, and roles, so Forgejo
Classroom does not reinvent authentication or membership. A classroom is backed
by a framework Team, which is how teachers, TAs, and students get their
permissions.

The client is the web UI teachers and students use. It talks to the server API
and nothing else.

Each classroom concept maps onto something the framework already has:

| Classroom concept | Backed by |
|---|---|
| Teachers, TAs, students | framework accounts, Team membership, roles |
| A classroom (one per Forgejo org) | a Team plus the linked `forgejo_org` |
| Roster entry | a record linking a school ID to a Forgejo login and an account |
| Assignment and its groups | assignment records pointing at a template repo |
| An accepted repository | a record tying a student or group to their repo |
| A grading run | one Forgejo Actions run and its score |

The full design rationale, including the Forgejo API call map, lives in
[server/OBJECT_PLAN.md](./server/OBJECT_PLAN.md).

## Requirements

- A Forgejo instance you administer, with Actions enabled and at least one
  runner registered.
- An access token on Forgejo for a service account that can create repos and
  teams in the org you will teach from.
- Python 3.11+ for the server, Node 20+ and pnpm for the client.

## Install and run

Server:

```bash
cd server
pip install -e "../../server-framework[all]"
pip install -e ".[dev]"
pytest extensions/        # 74 tests
python app.py             # serves on http://localhost:2100
```

Client:

```bash
cd client
pnpm install
pnpm dev                  # serves on http://localhost:1110
```

The client depends on the local `client-framework` (and `auth`, `dynamic-form`,
`zod2gql`) through pnpm's `link:` protocol. That is deliberate. A plain `file:`
install only copies the paths in each package's `files` list, and the framework
omits `src/components`, which its own code imports. `link:` symlinks the whole
source instead, so the build resolves.

## Configuration

The server reads everything from the environment. No secrets live in the repo.

| Variable | Purpose |
|---|---|
| `FORGEJO_BASE_URL` | Your Forgejo URL, e.g. `https://git.example.edu` |
| `FORGEJO_TOKEN` | Access token for the classroom service account |
| `CLASSROOM_API_URL` | Public URL of this app, injected into each student repo |
| `CLASSROOM_REPORT_TOKEN` | Shared token the autograder uses to report scores |
| `EGRESS_ALLOWED_HOSTS` | Include the Forgejo host here; the framework's SSRF guard blocks private hosts by default |
| `FORGEJO_CLIENT_ID`, `FORGEJO_CLIENT_SECRET` | Forgejo OAuth2 app credentials, for "Log in with Forgejo" |

## Usage

A term looks like this.

1. Create a classroom and point it at a Forgejo organization you own.
2. Import your roster. Paste a CSV with `identifier`, `name`, and
   `forgejo_username` columns; the first two are enough, and students can link
   their Forgejo account later.
3. Create an assignment. Pick a template repository (`owner/name` on Forgejo),
   set the points and deadline, and add a few autograding tests. Mark it as a
   group assignment if students work in teams.
4. Send students the invite link the assignment shows.

When a student opens the link and accepts:

- A repository is created from the template, named after the assignment and the
  student (or their group).
- The student gets write access, as a collaborator or through a Forgejo team.
- The autograder is committed into the repo, along with a Feedback pull request
  where you leave inline comments.

From then on, every push runs the tests and updates the student's score. Back in
the assignment view you can watch the gradebook fill in, re-run grading across
every repo, export grades as a CSV, or download a script that clones all of the
submissions at once.

## Autograding

When a student accepts, three files are committed into their repository:

- `.forgejo/workflows/autograde.yml`, a workflow that runs on every push.
- `.classroom/tests.json`, the test cases you defined for the assignment.
- `.classroom/grade.py`, a small grader that uses only the Python standard
  library, so it runs on any runner without extra dependencies.

Each push triggers the workflow. The grader runs each test, compares the output
(exact match, substring, or regex), adds up the points, and posts the result to
`CLASSROOM_API_URL/v1/grading_run/report`. That endpoint checks the shared
report token before recording anything, so a student cannot forge a grade. The
newest score shows up on the gradebook.

Two guardrails are built in. An assignment can mark files as protected, and the
grader fails the run if a student changes them, which keeps the tests honest. An
assignment can also enforce its deadline, which turns down new accepts once the
deadline has passed.

## Parity with GitHub Classroom

| GitHub Classroom feature | Status |
|---|---|
| Classrooms backed by an org | Yes |
| Teacher and TA roles | Yes, through framework teams |
| Roster with CSV import and account linking | Yes |
| Individual assignments | Yes |
| Group assignments, one team per group | Yes |
| Starter template repositories | Yes |
| Invite links | Yes |
| Public or private student repos | Yes |
| Deadlines with an optional hard cutoff | Yes |
| Autograding on push | Yes |
| Test presets: input/output and run-command | Yes |
| Feedback pull requests | Yes |
| Gradebook with status and scores | Yes |
| Grade export to CSV | Yes |
| Batch clone of all submissions | Yes |
| Re-run grading | Yes |
| Protected files | Yes |
| Log in with the git host | Yes, through the Forgejo OAuth2 provider |
| LMS sync over LTI | Not yet. CSV import covers the same ground for now |
| In-browser editor / Codespaces | Not applicable. Forgejo has no equivalent |

## Project status

Alpha. The server is covered by 74 tests and the client builds clean, but the
project has not yet run a real term end to end. Expect rough edges and treat the
schema as unstable.

## Contributing

Issues and pull requests are welcome. Run `pytest extensions/` in `server/` and
`pnpm build` in `client/` before you open a PR, and keep the server formatted
with `black`. Source files carry an SPDX header and the project is AGPL, so
contributions are under the same license.

## License

[AGPL-3.0-or-later](./LICENSE). Because it is a copyleft license, anyone who runs
a modified version as a network service has to publish their changes.

## Built on

Forgejo Classroom is a consumer of the Zephyrex server and client frameworks.
The frameworks handle accounts, storage, the API layer, and the OAuth2 provider;
this repository adds the classroom domain and the Forgejo integration on top.
