'use client';

import { useState } from 'react';
import { Feedback } from '@/components/feedback';
import { api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { OrganizationApplication } from '@/lib/types';
import { DecisionHistory, StatusBadge } from './shared';
import { ModerationReportQueue } from '@/features/moderation/report-queue';

function OrganizationAdminContent() {
  const {actor, token, authLoading, error: sessionError} = useSession();
  const canReviewApplications = actor?.eligible === true && actor.platform_admin;
  const applications = useApiResource<OrganizationApplication[]>(
    token && canReviewApplications ? '/platform-admin/organizations' : null,
    token,
  );
  const [workingOrgId, setWorkingOrgId] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<{orgName: string; message: string} | null>(null);
  const [lastDecision, setLastDecision] = useState<OrganizationApplication | null>(null);
  const applicationList = applications.data ?? [];

  async function decide(application: OrganizationApplication, outcome: 'approved' | 'rejected') {
    if (!token || workingOrgId) return;
    setWorkingOrgId(application.id);
    setDecisionError(null);
    setLastDecision(null);
    try {
      const result = await api<OrganizationApplication>(
        `/platform-admin/organizations/${encodeURIComponent(application.id)}/accreditation-decision`,
        {token, method: 'POST', body: {outcome}},
      );
      setLastDecision(result);
      applications.reload();
    } catch (requestError) {
      setDecisionError({
        orgName: application.name,
        message: requestError instanceof Error ? requestError.message : 'The decision could not be recorded.',
      });
      applications.reload();
    } finally {
      setWorkingOrgId(null);
    }
  }

  return (
    <>
      <p className="panel desktop-required" role="note">
        Accreditation review is available on desktop. Open this page on a wider screen to review applications.
      </p>
      <div className="management-desktop stack">
        <header className="page-heading">
          <p className="eyebrow">Platform administration</p>
          <h1>Organization applications</h1>
          <p className="muted">Record only the result of the offline accreditation assessment. This flow does not collect evidence, appeals, or reapplications.</p>
        </header>

        {authLoading ? <Feedback loading /> : !token ? (
          <section className="panel" role={sessionError ? 'alert' : undefined}>
            {sessionError?.message || 'Choose a local account in the header to continue.'}
          </section>
        ) : !canReviewApplications ? (
          <section className="panel" role="status">
            Platform admin access is required to review organization applications.
          </section>
        ) : (
          <>
            <ModerationReportQueue key={`platform:${token}`} token={token} />
            {lastDecision && (
              <section className="panel" role="status" aria-label="Recorded accreditation decision">
                <div className="actions">
                  <p><strong>{lastDecision.name}</strong> now has status</p>
                  <StatusBadge status={lastDecision.accreditation_status} />
                </div>
                <DecisionHistory decisions={lastDecision.decisions} />
              </section>
            )}
            {decisionError && (
              <div className="panel error" role="alert">
                <p>Decision request for {decisionError.orgName}: {decisionError.message}</p>
                <button className="button button-secondary" type="button" onClick={applications.reload}>
                  Refresh applications
                </button>
              </div>
            )}
            <section className="panel" aria-labelledby="applications-list-title">
              <h2 id="applications-list-title">Applications</h2>
              <Feedback loading={applications.loading} error={applications.error} onRetry={applications.reload}>
                {!applicationList.length ? (
                  <p className="empty-state muted">No applications were returned by the service.</p>
                ) : (
                  <div className="feed">
                    {applicationList.map(application => (
                      <article className="event-card" key={application.id}>
                        <header>
                          <h3>{application.name}</h3>
                          <StatusBadge status={application.accreditation_status} />
                        </header>
                        <p>{application.description || 'No description was provided.'}</p>
                        <p className="muted">
                          Submitted <time dateTime={application.created_at}>
                            {formatDate(application.created_at)} · {formatTime(application.created_at)} (Manila)
                          </time>
                        </p>
                        <DecisionHistory decisions={application.decisions} />
                        {application.accreditation_status === 'pending' && (
                          <div className="actions">
                            <button
                              className="button"
                              type="button"
                              disabled={workingOrgId !== null}
                              onClick={() => void decide(application, 'approved')}
                            >
                              {workingOrgId === application.id ? 'Saving…' : 'Approve after offline check'}
                            </button>
                            <button
                              className="button button-danger"
                              type="button"
                              disabled={workingOrgId !== null}
                              onClick={() => void decide(application, 'rejected')}
                            >
                              {workingOrgId === application.id ? 'Saving…' : 'Reject after offline check'}
                            </button>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )}
              </Feedback>
            </section>
          </>
        )}
      </div>
    </>
  );
}

export function OrganizationAdminPage() {
  const {version} = useSession();
  return <OrganizationAdminContent key={version} />;
}
