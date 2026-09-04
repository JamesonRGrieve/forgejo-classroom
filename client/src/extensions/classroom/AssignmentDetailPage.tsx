// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import { useMemo, useState } from 'react';
import { useClassroomApi, type Assignment, type AssignmentRepo, type AutogradeTest, type RosterEntry } from './api';
import { Alert, AsyncBoundary, Button, Card, Field, PageHeader, useAsync } from './components';

function idFromSlug(slug: string): string {
  return (slug.split('/')[1] ?? '');
}

function download(filename: string, content: string, mime = 'text/csv') {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function AssignmentDetailPage({ params }: { params: Record<string, string> }) {
  const assignmentId = idFromSlug(params.slug || '');
  const api = useClassroomApi();
  const assignment = useAsync<Assignment>(() => api.getAssignment(assignmentId), [assignmentId]);
  const repos = useAsync<AssignmentRepo[]>(() => api.listRepos(assignmentId), [assignmentId]);
  const tests = useAsync<AutogradeTest[]>(() => api.listTests(assignmentId), [assignmentId]);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function regrade() {
    setNotice(null);
    setError(null);
    try {
      const res = await api.regrade(assignmentId);
      setNotice(`Dispatched autograding for ${res.dispatched}/${res.total} repositories.`);
      repos.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function exportGrades() {
    setError(null);
    try {
      const res = await api.gradesCsv(assignmentId);
      download(res.filename || `grades-${assignmentId}.csv`, res.csv || '');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function cloneScript() {
    setError(null);
    try {
      const res = await api.submissions(assignmentId);
      download(`clone-${assignmentId}.sh`, res.clone_script || '', 'text/x-shellscript');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <main className="mx-auto max-w-5xl p-6">
      <AsyncBoundary state={assignment}>
        {(a) => (
          <PageHeader
            title={a.name || 'Assignment'}
            subtitle={[
              a.is_group ? 'Group assignment' : 'Individual assignment',
              `Invite: /accept/${a.id}`,
              a.points_possible != null ? `${a.points_possible} pts` : null,
            ]
              .filter(Boolean)
              .join(' · ')}
            actions={
              a.classroom_id ? (
                <a href={`/classroom/${a.classroom_id}`} className="text-sm underline-offset-2 hover:underline">
                  ← Classroom
                </a>
              ) : null
            }
          />
        )}
      </AsyncBoundary>

      {notice ? <Alert kind="success">{notice}</Alert> : null}
      {error ? <Alert kind="error">{error}</Alert> : null}

      <Card title="Gradebook">
        <div className="mb-4 flex flex-wrap gap-2">
          <Button onClick={regrade} variant="secondary">
            Re-run autograding
          </Button>
          <Button onClick={exportGrades} variant="secondary">
            Export grades (CSV)
          </Button>
          <Button onClick={cloneScript} variant="secondary">
            Download clone script
          </Button>
        </div>
        <GradeTable assignmentId={assignmentId} repos={repos} />
      </Card>

      <AutogradeTestsSection assignmentId={assignmentId} tests={tests} />
    </main>
  );
}

function GradeTable({
  assignmentId,
  repos,
}: {
  assignmentId: string;
  repos: ReturnType<typeof useAsync<AssignmentRepo[]>>;
}) {
  const api = useClassroomApi();
  const classroomId = ''; // roster is fetched per-assignment via repos' classroom; see note below
  // Roster is keyed by classroom; fetch it lazily off the first repo's assignment.
  const roster = useAsync<RosterEntry[]>(async () => {
    const list = repos.data ?? (await api.listRepos(assignmentId));
    const first = list[0];
    if (!first?.assignment_id) {
      return [];
    }
    const assignment = await api.getAssignment(first.assignment_id);
    return assignment.classroom_id ? api.listRoster(assignment.classroom_id) : [];
  }, [assignmentId, repos.data]);

  const rosterById = useMemo(() => {
    const map: Record<string, RosterEntry> = {};
    for (const r of roster.data ?? []) {
      map[r.id] = r;
    }
    return map;
  }, [roster.data]);

  void classroomId;

  return (
    <AsyncBoundary state={repos}>
      {(list) =>
        list.length === 0 ? (
          <p className="text-sm text-muted-foreground">No submissions yet. Share the invite link with students.</p>
        ) : (
          <table className="w-full text-sm">
            <caption className="sr-only">Submissions and scores</caption>
            <thead>
              <tr className="border-b border-border text-left">
                <th scope="col" className="py-2">Participant</th>
                <th scope="col" className="py-2">Repository</th>
                <th scope="col" className="py-2">Status</th>
                <th scope="col" className="py-2">Score</th>
              </tr>
            </thead>
            <tbody>
              {list.map((r) => {
                const entry = r.roster_entry_id ? rosterById[r.roster_entry_id] : undefined;
                const who = entry?.display_name || entry?.forgejo_username || (r.assignment_group_id ? 'Group' : '—');
                return (
                  <tr key={r.id} className="border-b border-border/50">
                    <td className="py-2">{who}</td>
                    <td className="py-2">
                      {r.repo_full_name ? (
                        <code className="text-xs">{r.repo_full_name}</code>
                      ) : (
                        <span className="text-muted-foreground">not provisioned</span>
                      )}
                    </td>
                    <td className="py-2">{r.status || '—'}</td>
                    <td className="py-2">{r.latest_score != null ? r.latest_score : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )
      }
    </AsyncBoundary>
  );
}

function AutogradeTestsSection({
  assignmentId,
  tests,
}: {
  assignmentId: string;
  tests: ReturnType<typeof useAsync<AutogradeTest[]>>;
}) {
  const api = useClassroomApi();
  const [name, setName] = useState('');
  const [run, setRun] = useState('');
  const [expected, setExpected] = useState('');
  const [points, setPoints] = useState('1');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function addTest() {
    if (!name.trim() || !run.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.createTest({
        assignment_id: assignmentId,
        name: name.trim(),
        run: run.trim(),
        expected_output: expected || undefined,
        comparison: 'included',
        points: Number(points) || 1,
      });
      setName('');
      setRun('');
      setExpected('');
      setPoints('1');
      tests.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Autograding tests">
      {error ? <Alert kind="error">{error}</Alert> : null}
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Field label="Test name" id="t-name" value={name} onChange={setName} placeholder="prints hello" required />
        <Field label="Points" id="t-points" value={points} onChange={setPoints} type="number" />
        <Field label="Run command" id="t-run" value={run} onChange={setRun} placeholder="python hello.py" required />
        <Field label="Expected output" id="t-expected" value={expected} onChange={setExpected} placeholder="hello" />
      </div>
      <Button onClick={addTest} disabled={busy || !name.trim() || !run.trim()}>
        {busy ? 'Adding…' : 'Add test'}
      </Button>

      <div className="mt-4">
        <AsyncBoundary state={tests}>
          {(list) =>
            list.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No tests yet. Tests are injected into each accepted repo and run on every push.
              </p>
            ) : (
              <ul className="divide-y divide-border">
                {list.map((t) => (
                  <li key={t.id} className="py-2 text-sm">
                    <span className="font-medium">{t.name}</span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {t.points ?? 1} pts · <code>{t.run}</code>
                    </span>
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
