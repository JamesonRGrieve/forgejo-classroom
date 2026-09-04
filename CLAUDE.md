# Forgejo Classroom

GitHub-Classroom-equivalent for Forgejo, built as a **Zephyrex framework
consumer** (not a fork of Forgejo, not a fork of the framework).

## Stack standards — read before your first edit

- Python (server): `/home/jameson/Source/ai-prompts/python.md`
- TypeScript (client): `/home/jameson/Source/ai-prompts/typescript.md`
- React/Next (client): `/home/jameson/Source/ai-prompts/react-next.md`

## Architecture (target state)

Forgejo has no server-side plugin seam, so this is a **companion runtime**:
a Zephyrex consumer app beside an unmodified Forgejo, driving it over the
Forgejo REST API, webhooks, Forgejo Actions, and OAuth2 provider.

- `server/` — the `classroom` domain extension on ServerFramework. Owns
  the domain; the framework supplies auth (User/Team/Role) and
  auto-generates REST + GraphQL CRUD. Membership/roles are **not**
  reinvented — a classroom is backed by a framework `Team`.
- `client/` — the `classroom` client extension on client-framework
  (teacher dashboard, nav, settings).

Authoritative design + Forgejo wiring map: `server/OBJECT_PLAN.md`.

## Conventions

- Mirror the sibling consumer `zephyrex-rpg` for structure and idioms.
- Follow the framework model DSL exactly (`ApplicationModel`,
  `*.Reference` mixins, `ModelMeta`, `Create`/`Update`/`Search`, closed
  enums as Pydantic `Literal`s) — it wins over generic style where they
  differ, because the DSL is introspected at runtime.
- One extension owns the domain (`classroom`); add owned tables to
  `ALL_MODELS` and bump the count assertion in the extension test.
- AGPL-3.0-or-later, SPDX header on every source file.
- No secrets in the repo — the Forgejo API token and OAuth secrets come
  from the environment / OpenBao at runtime.

## Commands

```bash
# server
cd server && pip install -e "../../server-framework[all]" && pip install -e ".[dev]"
pytest extensions/

# client
cd client && pnpm install && pnpm dev
```
