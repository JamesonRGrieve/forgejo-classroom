// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import { useState } from 'react';
import { useUser } from 'zephyrex';
import { useClassroomApi } from './api';
import { Alert, Button, Card, Field, PageHeader } from './components';

function idFromSlug(slug: string): string {
  return (slug.split('/')[1] ?? '');
}

export function AcceptPage({ params }: { params: Record<string, string> }) {
  const assignmentId = idFromSlug(params.slug || '');
  const api = useClassroomApi();
  const user = useUser() as { username?: string } | null;
  const [username, setUsername] = useState(user?.username ?? '');
  const [groupName, setGroupName] = useState('');
  const [result, setResult] = useState<{ repo_full_name?: string; html_url?: string; status?: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function accept() {
    setBusy(true);
    setError(null);
    try {
      const res = (await api.accept(assignmentId, {
        forgejo_username: username.trim() || undefined,
        group_name: groupName.trim() || undefined,
      })) as { repo_full_name?: string; html_url?: string; status?: string };
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-lg p-6">
      <PageHeader title="Accept assignment" subtitle="Accept to create your repository from the starter template." />

      <Card>
        {error ? <Alert kind="error">{error}</Alert> : null}
        {result ? (
          <Alert kind="success">
            {result.status === 'already_accepted' ? 'You already accepted this assignment.' : 'Repository ready!'}{' '}
            {result.html_url ? (
              <a href={result.html_url} className="font-medium underline-offset-2 hover:underline">
                Open {result.repo_full_name}
              </a>
            ) : (
              result.repo_full_name
            )}
          </Alert>
        ) : (
          <>
            <Field
              label="Your Forgejo username"
              id="accept-username"
              value={username}
              onChange={setUsername}
              placeholder="ada"
              required
            />
            <Field
              label="Group name (group assignments only)"
              id="accept-group"
              value={groupName}
              onChange={setGroupName}
              placeholder="team-rocket"
            />
            <Button onClick={accept} disabled={busy || !username.trim()}>
              {busy ? 'Provisioning…' : 'Accept this assignment'}
            </Button>
          </>
        )}
      </Card>
    </main>
  );
}
