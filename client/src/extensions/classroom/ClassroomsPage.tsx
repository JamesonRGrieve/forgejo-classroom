// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import { useState } from 'react';
import { useClassroomApi, type Classroom } from './api';
import { Alert, AsyncBoundary, Button, Card, Field, PageHeader, useAsync } from './components';

export function ClassroomsPage() {
  const api = useClassroomApi();
  const state = useAsync<Classroom[]>(() => api.listClassrooms(), []);
  const [name, setName] = useState('');
  const [org, setOrg] = useState('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create() {
    if (!name.trim()) {
      return;
    }
    setCreating(true);
    setError(null);
    try {
      await api.createClassroom({ name: name.trim(), forgejo_org: org.trim() || undefined });
      setName('');
      setOrg('');
      state.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <main className="mx-auto max-w-4xl p-6">
      <PageHeader title="Classrooms" subtitle="Each classroom is backed by a Forgejo organization." />

      <Card title="New classroom">
        {error ? <Alert kind="error">{error}</Alert> : null}
        <Field label="Name" id="cr-name" value={name} onChange={setName} placeholder="CMPUT 174 — Fall 2026" required />
        <Field label="Forgejo organization" id="cr-org" value={org} onChange={setOrg} placeholder="cmput174-f26" />
        <Button onClick={create} disabled={creating || !name.trim()}>
          {creating ? 'Creating…' : 'Create classroom'}
        </Button>
      </Card>

      <Card title="Your classrooms">
        <AsyncBoundary state={state}>
          {(classrooms) =>
            classrooms.length === 0 ? (
              <p className="text-sm text-muted-foreground">No classrooms yet.</p>
            ) : (
              <ul className="divide-y divide-border">
                {classrooms.map((c) => (
                  <li key={c.id} className="flex items-center justify-between py-3">
                    <div>
                      <a href={`/classroom/${c.id}`} className="font-medium underline-offset-2 hover:underline">
                        {c.name || c.id}
                      </a>
                      {c.forgejo_org ? <span className="ml-2 text-xs text-muted-foreground">@{c.forgejo_org}</span> : null}
                    </div>
                    {c.archived ? <span className="text-xs text-muted-foreground">archived</span> : null}
                  </li>
                ))}
              </ul>
            )
          }
        </AsyncBoundary>
      </Card>
    </main>
  );
}
