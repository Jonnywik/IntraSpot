import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import type { OrganizationApplication } from '@/lib/types';

type AccreditationDecision = OrganizationApplication['decisions'][number];

export function StatusBadge({status}: {status: string}) {
  const t = useT();
  const className = status === 'pending'
    ? 'status-chip pending'
    : status === 'rejected'
      ? 'status-chip cancelled'
      : 'status-chip';

  const label = t(status);
  return <span className={className}>{label.charAt(0).toUpperCase() + label.slice(1)}</span>;
}

export function DecisionHistory({decisions}: {decisions: AccreditationDecision[]}) {
  const t = useT();
  const {preferences: {language}} = usePreferences();
  return (
    <section aria-label={t('Accreditation decision history')}>
      <h3>{t('Accreditation decisions')}</h3>
      {decisions.length === 0 ? (
        <p className="muted">{t('No platform decision has been recorded.')}</p>
      ) : (
        <ol className="stack">
          {decisions.map(decision => (
            <li key={decision.id}>
              <div className="actions">
                <StatusBadge status={decision.outcome} />
                <small>{t('Platform admin ID: {id}', {id: decision.admin_id})}</small>
              </div>
              <small>
                <time dateTime={decision.decided_at}>
                  {formatDate(decision.decided_at, language)} · {formatTime(decision.decided_at, language)} ({t('Manila time')})
                </time>
              </small>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
