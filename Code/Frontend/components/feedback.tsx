import type { ReactNode } from 'react';
export function Feedback({loading, error, onRetry, children}: {
  loading?: boolean; error?: Error | null; onRetry?: () => void; children?: ReactNode;
}) {
  if (loading) return <p role="status" className="panel muted">Loading…</p>;
  if (error) return <div role="alert" className="panel error"><p>{error.message}</p>{onRetry && <button className="button button-secondary" onClick={onRetry}>Retry</button>}</div>;
  return <>{children}</>;
}
