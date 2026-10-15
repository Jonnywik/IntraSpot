import { formatDate, formatTime } from '@/lib/date';
import type { OrganizationApplication } from '@/lib/types';

type AccreditationDecision = OrganizationApplication['decisions'][number];

export function StatusBadge({status}: {status: string}) {
  const className = status === 'pending'
    ? 'status-chip pending'
    : status === 'rejected'
      ? 'status-chip cancelled'
      : 'status-chip';

  return <span className={className}>{status.charAt(0).toUpperCase() + status.slice(1)}</span>;
}

export function DecisionHistory({decisions}: {decisions: AccreditationDecision[]}) {
  return (
    <section aria-label="Accreditation decision history">
      <h3>Accreditation decisions</h3>
      {decisions.length === 0 ? (
        <p className="muted">No platform decision has been recorded.</p>
      ) : (
        <ol className="stack">
          {decisions.map(decision => (
            <li key={decision.id}>
              <div className="actions">
                <StatusBadge status={decision.outcome} />
                <small>Platform admin ID: {decision.admin_id}</small>
              </div>
              <small>
                <time dateTime={decision.decided_at}>
                  {formatDate(decision.decided_at)} · {formatTime(decision.decided_at)} (Manila)
                </time>
              </small>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
