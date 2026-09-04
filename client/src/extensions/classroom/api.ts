// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import { useClient } from 'zephyrex';

// Domain shapes (mirror the server classroom extension models). Optional
// everywhere because the framework's CRUD responses are permissive.
export interface Classroom {
  id: string;
  name?: string;
  description?: string;
  forgejo_org?: string;
  archived?: boolean;
}

export interface RosterEntry {
  id: string;
  classroom_id?: string;
  identifier?: string;
  display_name?: string;
  forgejo_username?: string;
  linked_at?: string | null;
}

export interface Assignment {
  id: string;
  classroom_id?: string;
  name?: string;
  slug?: string;
  template_repo?: string;
  is_group?: boolean;
  deadline?: string | null;
  enforce_deadline?: boolean;
  protected_paths?: string;
  points_possible?: number | null;
  visibility?: 'private' | 'public';
  invite_enabled?: boolean;
}

export interface AssignmentRepo {
  id: string;
  assignment_id?: string;
  roster_entry_id?: string | null;
  assignment_group_id?: string | null;
  repo_full_name?: string | null;
  status?: string;
  latest_score?: number | null;
  submission_sha?: string | null;
}

export interface AutogradeTest {
  id: string;
  assignment_id?: string;
  name?: string;
  run?: string;
  input?: string;
  expected_output?: string;
  comparison?: 'included' | 'exact' | 'regex';
  points?: number;
}

// The framework's LIST/CREATE responses come back in a few shapes; normalize
// defensively so the UI is resilient to wrapper conventions.
function asList<T>(res: unknown): T[] {
  if (Array.isArray(res)) {
    return res as T[];
  }
  if (res && typeof res === 'object') {
    const obj = res as Record<string, unknown>;
    for (const key of ['items', 'data', 'results', 'records']) {
      if (Array.isArray(obj[key])) {
        return obj[key] as T[];
      }
    }
  }
  return [];
}

function asOne<T>(res: unknown, resource: string): T {
  if (res && typeof res === 'object') {
    const obj = res as Record<string, unknown>;
    if (obj[resource] && typeof obj[resource] === 'object') {
      return obj[resource] as T;
    }
  }
  return res as T;
}

export interface ClassroomApi {
  listClassrooms(): Promise<Classroom[]>;
  createClassroom(body: Partial<Classroom>): Promise<Classroom>;
  getClassroom(id: string): Promise<Classroom>;
  importRoster(classroomId: string, csv: string): Promise<{ imported: number; updated: number; parsed: number }>;
  listRoster(classroomId: string): Promise<RosterEntry[]>;
  listAssignments(classroomId: string): Promise<Assignment[]>;
  createAssignment(body: Partial<Assignment>): Promise<Assignment>;
  getAssignment(id: string): Promise<Assignment>;
  listRepos(assignmentId: string): Promise<AssignmentRepo[]>;
  listTests(assignmentId: string): Promise<AutogradeTest[]>;
  createTest(body: Partial<AutogradeTest>): Promise<AutogradeTest>;
  accept(assignmentId: string, body: { forgejo_username?: string; group_name?: string }): Promise<Record<string, unknown>>;
  regrade(assignmentId: string): Promise<{ dispatched: number; total: number }>;
  gradesCsv(assignmentId: string): Promise<{ filename: string; csv: string }>;
  submissions(assignmentId: string): Promise<{ repos: Array<{ repo_full_name: string; clone_url: string }>; clone_script: string }>;
}

export function useClassroomApi(): ClassroomApi {
  const client = useClient();
  return {
    async listClassrooms() {
      return asList<Classroom>(await client.get('/v1/classroom'));
    },
    async createClassroom(body) {
      return asOne<Classroom>(await client.post('/v1/classroom', body), 'classroom');
    },
    async getClassroom(id) {
      return asOne<Classroom>(await client.get(`/v1/classroom/${id}`), 'classroom');
    },
    async importRoster(classroomId, csv) {
      return client.post(`/v1/classroom/${classroomId}/roster/import`, { csv });
    },
    async listRoster(classroomId) {
      return asList<RosterEntry>(await client.get('/v1/roster_entry', { classroom_id: classroomId }));
    },
    async listAssignments(classroomId) {
      return asList<Assignment>(await client.get('/v1/assignment', { classroom_id: classroomId }));
    },
    async createAssignment(body) {
      return asOne<Assignment>(await client.post('/v1/assignment', body), 'assignment');
    },
    async getAssignment(id) {
      return asOne<Assignment>(await client.get(`/v1/assignment/${id}`), 'assignment');
    },
    async listRepos(assignmentId) {
      return asList<AssignmentRepo>(await client.get('/v1/assignment_repo', { assignment_id: assignmentId }));
    },
    async listTests(assignmentId) {
      return asList<AutogradeTest>(await client.get('/v1/autograde_test', { assignment_id: assignmentId }));
    },
    async createTest(body) {
      return asOne<AutogradeTest>(await client.post('/v1/autograde_test', body), 'autograde_test');
    },
    async accept(assignmentId, body) {
      return client.post(`/v1/assignment/${assignmentId}/accept`, body);
    },
    async regrade(assignmentId) {
      return client.post(`/v1/assignment/${assignmentId}/regrade`);
    },
    async gradesCsv(assignmentId) {
      return client.get(`/v1/assignment/${assignmentId}/grades.csv`);
    },
    async submissions(assignmentId) {
      return client.get(`/v1/assignment/${assignmentId}/submissions`);
    },
  };
}
