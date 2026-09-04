# SPDX-License-Identifier: AGPL-3.0-or-later
"""classroom extension.

GitHub-Classroom-equivalent domain for Forgejo, implemented as a Zephyrex
consumer extension. The framework supplies identity (User), tenancy and
RBAC (Team, Role), and auto-generates REST + GraphQL CRUD for every model
declared in ``BLL_Classroom``. This extension owns only the classroom
domain and leaves Forgejo unmodified — Forgejo is driven externally over
its REST API and Forgejo Actions (see ``OBJECT_PLAN.md`` for the
companion-runtime wiring).
"""
