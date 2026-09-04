// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import { useState } from 'react';
import { useClassroomApi, type Assignment, type Classroom, type RosterEntry } from './api';
import { Alert, AsyncBoundary, Button, Card, Checkbox, Field, PageHeader, TextArea, useAsync } from './components';

function idFromSlug(slug: string): string {
  const parts = slug.split('/');
  return parts[1] ?? '';
}

export function ClassroomDetailPage({ params }: { params: Record<string, string> }) {
  const classroomId = idFromSlug(params.slug || '');
  const api = useClassroomApi();
  const classroom = useAsync<Classroom>(() => api.getClassroom(classroomId), [classroomId]);
  const roster = useAsync<RosterEntry[]>(() => api.listRoster(classroomId), [classroomId]);
  const assignments = useAsync<Assignment[]>(() => api.listAssignments(classroomId), [classroomId]);

  return (
    <main className="mx-auto max-w-5xl p-6">
      <AsyncBoundary state={classroom}>
        {(c) => (
          <PageHeader
            title={c.name || 'Classroom'}
            subtitle={c.forgejo_org ? `Forgejo organization: ${c.forgejo_org}` : 'No Forgejo organization linked'}
            actions={
              <a href="/classroom" className="text-sm underline-offset-2 hover:underline">
                ← All classrooms
              </a>
            }
          />
        )}
      </AsyncBoundary>

      <RosterSection classroomId={classroomId} roster={roster} />
      <AssignmentsSection classroomId={classroomId} assignments={assignments} />
    </main>
  );
}

function RosterSection({
  classroomId,
  roster,
}: {
  classroomId: string;
  roster: ReturnType<typeof useAsync<RosterEntry[]>>;
}) {
  const api = useClassroomApi();
  const [csv, setCsv] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function importCsv() {
    setBusy(true);
    setMsg(null);
    setError(null);
    try {
      const res = await api.importRoster(classroomId, csv);
      setMsg(`Imported ${res.imported}, updated ${res.updated} of ${res.parsed} parsed rows.`);
      setCsv('');
      roster.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Roster">
      {msg ? <Alert kind="success">{msg}</Alert> : null}
      {error ? <Alert kind="error">{error}</Alert> : null}
      <TextArea
        label="Import CSV (headers: identifier, name, forgejo_username)"
        id="roster-csv"
        value={csv}
        onChange={setCsv}
        placeholder={'identifier,name,forgejo_username\n1234,Ada Lovelace,ada'}
      />
      <Button onClick={importCsv} disabled={busy || !csv.trim()}>
        {busy ? 'Importing…' : 'Import roster'}
      </Button>

      <div className="mt-4">
        <AsyncBoundary state={roster}>
          {(entries) =>
            entries.length === 0 ? (
              <p className="text-sm text-muted-foreground">No roster entries yet.</p>
            ) : (
              <table className="w-full text-sm">
                <caption className="sr-only">Roster entries</caption>
                <thead>
                  <tr className="border-b border-border text-left">
                    <th scope="col" className="py-2">Identifier</th>
                    <th scope="col" className="py-2">Name</th>
                    <th scope="col" className="py-2">Forgejo</th>
                    <th scope="col" className="py-2">Linked</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((e) => (
                    <tr key={e.id} className="border-b border-border/50">
                      <td className="py-2">{e.identifier}</td>
                      <td className="py-2">{e.display_name || '—'}</td>
                      <td className="py-2">{e.forgejo_username || '—'}</td>
                      <td className="py-2">{e.linked_at ? 'yes' : 'no'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          }
        </AsyncBoundary>
      </div>
    </Card>
  );
}

function AssignmentsSection({
  classroomId,
  assignments,
}: {
  classroomId: string;
  assignments: ReturnType<typeof useAsync<Assignment[]>>;
}) {
  const api = useClassroomApi();
  const [name, setName] = useState('');
  const [template, setTemplate] = useState('');
  const [slug, setSlug] = useState('');
  const [isGroup, setIsGroup] = useState(false);
  const [points, setPoints] = useState('');
  const [deadline, setDeadline] = useState('');
  const [enforceDeadline, setEnforceDeadline] = useState(false);
  const [protectedPaths, setProtectedPaths] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function create() {
    if (!name.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createAssignment({
        classroom_id: classroomId,
        name: name.trim(),
        template_repo: template.trim() || undefined,
        slug: slug.trim() || undefined,
        is_group: isGroup,
        points_possible: points ? Number(points) : undefined,
        deadline: deadline ? new Date(deadline).toISOString() : undefined,
        enforce_deadline: enforceDeadline,
        protected_paths: protectedPaths.trim() || undefined,
      });
      setName('');
      setTemplate('');
      setSlug('');
      setPoints('');
      setDeadline('');
      setEnforceDeadline(false);
      setProtectedPaths('');
      setIsGroup(false);
      assignments.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Assignments">
      {error ? <Alert kind="error">{error}</Alert> : null}
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Field label="Name" id="a-name" value={name} onChange={setName} placeholder="Lab 1" required />
        <Field label="Invite slug" id="a-slug" value={slug} onChange={setSlug} placeholder="lab-1" />
        <Field label="Template repo (owner/name)" id="a-template" value={template} onChange={setTemplate} placeholder="cmput174-f26/lab1-starter" />
        <Field label="Points possible" id="a-points" value={points} onChange={setPoints} type="number" />
        <Field label="Deadline" id="a-deadline" value={deadline} onChange={setDeadline} type="datetime-local" />
      </div>
      <Field
        label="Protected paths (globs, comma/newline-separated)"
        id="a-protected"
        value={protectedPaths}
        onChange={setProtectedPaths}
        placeholder="tests/**, .classroom/**"
      />
      <Checkbox label="Group assignment" id="a-group" checked={isGroup} onChange={setIsGroup} />
      <Checkbox label="Enforce deadline (reject accepts after the deadline)" id="a-enforce" checked={enforceDeadline} onChange={setEnforceDeadline} />
      <Button onClick={create} disabled={busy || !name.trim()}>
        {busy ? 'Creating…' : 'Create assignment'}
      </Button>

      <div className="mt-4">
        <AsyncBoundary state={assignments}>
          {(list) =>
            list.length === 0 ? (
              <p className="text-sm text-muted-foreground">No assignments yet.</p>
            ) : (
              <ul className="divide-y divide-border">
                {list.map((a) => (
                  <li key={a.id} className="flex items-center justify-between py-3">
                    <div>
                      <a href={`/assignment/${a.id}`} className="font-medium underline-offset-2 hover:underline">
                        {a.name || a.id}
                      </a>
                      <span className="ml-2 text-xs text-muted-foreground">
                        {a.is_group ? 'group' : 'individual'}
                        {` · invite: /accept/${a.id}`}
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground">{a.invite_enabled === false ? 'invites closed' : 'open'}</span>
                  </li>
                ))}
              </ul>
            )
          }
        </AsyncBoundary>
      </div>
    </Card>
  );
}
