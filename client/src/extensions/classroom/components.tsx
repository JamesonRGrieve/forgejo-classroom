// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import { useCallback, useEffect, useState, type ReactNode } from 'react';

// Minimal, accessible, tailwind-styled primitives. Kept local so the
// extension has no hard dependency on a specific shadcn component API.

interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
  reload: () => void;
}

export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  const run = useCallback(fn, deps);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    run()
      .then((res) => {
        if (live) {
          setData(res);
        }
      })
      .catch((err: unknown) => {
        if (live) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (live) {
          setLoading(false);
        }
      });
    return () => {
      live = false;
    };
  }, [run, tick]);

  return { data, loading, error, reload: () => setTick((t) => t + 1) };
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="mb-6 flex items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {subtitle ? <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex gap-2">{actions}</div> : null}
    </header>
  );
}

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="mb-6 rounded-lg border border-border bg-card p-5 shadow-sm">
      {title ? <h2 className="mb-3 text-lg font-semibold">{title}</h2> : null}
      {children}
    </section>
  );
}

export function Button({
  children,
  onClick,
  type = 'button',
  variant = 'primary',
  disabled,
}: {
  children: ReactNode;
  onClick?: () => void;
  type?: 'button' | 'submit';
  variant?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
}) {
  const styles: Record<string, string> = {
    primary: 'bg-primary text-primary-foreground hover:opacity-90',
    secondary: 'border border-border bg-background hover:bg-muted',
    danger: 'bg-destructive text-destructive-foreground hover:opacity-90',
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50 ${styles[variant]}`}
    >
      {children}
    </button>
  );
}

export function Field({
  label,
  id,
  value,
  onChange,
  placeholder,
  type = 'text',
  required,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
  required?: boolean;
}) {
  return (
    <div className="mb-3 flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      <input
        id={id}
        type={type}
        value={value}
        required={required}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-background px-3 py-2 text-sm"
      />
    </div>
  );
}

export function TextArea({
  label,
  id,
  value,
  onChange,
  placeholder,
  rows = 6,
}: {
  label: string;
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <div className="mb-3 flex flex-col gap-1">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      <textarea
        id={id}
        value={value}
        rows={rows}
        placeholder={placeholder}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-md border border-border bg-background px-3 py-2 font-mono text-xs"
      />
    </div>
  );
}

export function Checkbox({ label, id, checked, onChange }: { label: string; id: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <input id={id} type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="h-4 w-4" />
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
    </div>
  );
}

export function Alert({ kind = 'info', children }: { kind?: 'info' | 'error' | 'success'; children: ReactNode }) {
  const styles: Record<string, string> = {
    info: 'border-border bg-muted text-foreground',
    error: 'border-destructive/40 bg-destructive/10 text-destructive',
    success: 'border-green-600/40 bg-green-600/10 text-green-700',
  };
  return (
    <div role={kind === 'error' ? 'alert' : 'status'} className={`mb-4 rounded-md border px-4 py-3 text-sm ${styles[kind]}`}>
      {children}
    </div>
  );
}

export function AsyncBoundary<T>({ state, children }: { state: { data: T | null; loading: boolean; error: string | null }; children: (data: T) => ReactNode }) {
  if (state.loading) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }
  if (state.error) {
    return <Alert kind="error">{state.error}</Alert>;
  }
  if (state.data === null) {
    return null;
  }
  return <>{children(state.data)}</>;
}
