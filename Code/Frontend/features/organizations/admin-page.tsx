'use client';

import { useEffect, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { formatDate, formatTime } from '@/lib/date';
import { useT } from '@/lib/i18n';
import { usePreferences } from '@/lib/preferences';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { OrganizationApplication } from '@/lib/types';
import { ModerationReportQueue } from '@/features/moderation/report-queue';
import { AnnouncementReportQueue } from '@/features/moderation/AnnouncementReportQueue';
import styles from './platform-admin.module.css';

type ApplicationStatus = 'pending' | 'approved' | 'rejected';
type StatusFilter = 'all' | ApplicationStatus;
type PendingDecision = {application: OrganizationApplication; outcome: 'approved' | 'rejected'};
type AccreditationDecision = OrganizationApplication['decisions'][number];

const statusFilters: {key: StatusFilter; label: string}[] = [
  {key: 'all', label: 'All'},
  {key: 'pending', label: 'Pending'},
  {key: 'approved', label: 'Approved'},
  {key: 'rejected', label: 'Rejected'},
];

function ApplicationStatusBadge({status}: {status: string}) {
  const t = useT();
  const className = status === 'pending'
    ? styles.pending
    : status === 'rejected'
      ? styles.rejected
      : styles.approved;

  return <span className={styles.status + ' ' + className}>{t(status)}</span>;
}

function DecisionHistory({decisions}: {decisions: AccreditationDecision[]}) {
  const t = useT();
  const {preferences} = usePreferences();

  return (
    <section className={styles.history} aria-label={t('Accreditation decision history')}>
      <h4>{t('Decision history')}</h4>
      {decisions.length === 0 ? (
        <p className={styles.muted}>{t('No decision has been recorded.')}</p>
      ) : (
        <ol className={styles.historyList}>
          {decisions.map(decision => (
            <li key={decision.id}>
              <div className={styles.historyHeading}>
                <ApplicationStatusBadge status={decision.outcome} />
                <span>
                  {t('Platform admin ID')}: <span className={styles.identifier}>{decision.admin_id}</span>
                </span>
              </div>
              <time dateTime={decision.decided_at}>
                {formatDate(decision.decided_at, preferences.language)} · {formatTime(decision.decided_at, preferences.language)} ({t('Manila time')})
              </time>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function OrganizationAdminContent() {
  const t = useT();
  const {preferences} = usePreferences();
  const {actor, token, authLoading, error: sessionError} = useSession();
  const canReviewApplications = actor?.eligible === true && actor.platform_admin;
  const applications = useApiResource<OrganizationApplication[]>(
    token && canReviewApplications ? '/platform-admin/organizations' : null,
    token,
  );
  const [workingOrgId, setWorkingOrgId] = useState<string | null>(null);
  const [decisionError, setDecisionError] = useState<{orgName: string; message: string} | null>(null);
  const [lastDecision, setLastDecision] = useState<OrganizationApplication | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [search, setSearch] = useState('');
  const [pendingDecision, setPendingDecision] = useState<PendingDecision | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const applicationList = applications.data ?? [];
  const applicationCounts = {all: applicationList.length, pending: 0, approved: 0, rejected: 0};

  for (const application of applicationList) {
    if (application.accreditation_status === 'pending') applicationCounts.pending += 1;
    if (application.accreditation_status === 'approved') applicationCounts.approved += 1;
    if (application.accreditation_status === 'rejected') applicationCounts.rejected += 1;
  }

  const normalizedSearch = search.trim().toLocaleLowerCase();
  const visibleApplications = applicationList.filter(application => {
    const matchesStatus = statusFilter === 'all' || application.accreditation_status === statusFilter;
    const matchesSearch = !normalizedSearch ||
      (application.name + ' ' + application.description).toLocaleLowerCase().includes(normalizedSearch);
    return matchesStatus && matchesSearch;
  });

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    const desktopQuery = window.matchMedia('(min-width: 768px)');
    const syncDialog = () => {
      if (!desktopQuery.matches) {
        if (dialog.open) dialog.close();
        setPendingDecision(null);
      } else if (pendingDecision && !dialog.open) {
        dialog.showModal();
      } else if (!pendingDecision && dialog.open) {
        dialog.close();
      }
    };
    syncDialog();
    desktopQuery.addEventListener('change', syncDialog);
    return () => desktopQuery.removeEventListener('change', syncDialog);
  }, [pendingDecision]);

  async function decide(application: OrganizationApplication, outcome: 'approved' | 'rejected') {
    if (!token || workingOrgId || application.accreditation_status !== 'pending') return;
    setWorkingOrgId(application.id);
    setDecisionError(null);
    setLastDecision(null);
    try {
      const result = await api<OrganizationApplication>(
        '/platform-admin/organizations/' + encodeURIComponent(application.id) + '/accreditation-decision',
        {token, method: 'POST', body: {outcome}},
      );
      setLastDecision(result);
      setPendingDecision(null);
      applications.reload();
    } catch (requestError) {
      const message = requestError instanceof Error && requestError.message
        ? requestError.message
        : t('The decision could not be confirmed. Refresh the application list and check its history before proceeding.');
      setDecisionError({orgName: application.name, message});
      setPendingDecision(null);
      applications.reload();
    } finally {
      setWorkingOrgId(null);
    }
  }

  return (
    <>
      <p className={'panel desktop-required ' + styles.mobileNotice} role="note">
        {t('Accreditation review is available on desktop. Open this page on a wider screen to review applications.')}
      </p>
      <div className={'management-desktop ' + styles.page}>
        <header className={styles.heading}>
          <p className="eyebrow">{t('Platform administration')}</p>
          <h1>{t('Organization applications')}</h1>
          <p className={styles.muted}>{t('Review organization accreditation applications and platform safety reports.')}</p>
        </header>

        {authLoading ? (
          <p className="panel" role="status">{t('Checking platform access…')}</p>
        ) : !token ? (
          <section className="panel" role={sessionError ? 'alert' : undefined}>
            {sessionError?.message || t('Sign in using the site header to continue.')}
          </section>
        ) : !canReviewApplications ? (
          <section className="panel" role="status">
            {t('Platform admin access is required to review organization applications.')}
          </section>
        ) : (
          <>
            <aside className={styles.assessmentNote} aria-labelledby="offline-assessment-title">
              <h2 id="offline-assessment-title">{t('Offline accreditation assessment')}</h2>
              <p>{t('Assess the organization’s accreditation with the academy outside IntraSpot. This interface records your decision; it does not collect or verify supporting evidence.')}</p>
              <p>{t('An organization’s LinkedIn profile is not evidence of accreditation.')}</p>
            </aside>

            {lastDecision && (
              <section className={'panel ' + styles.recordedDecision} aria-labelledby="recorded-decision-title">
                <div className={styles.recordedHeading}>
                  <div>
                    <p className="eyebrow" role="status">
                      {t('Decision recorded for {name}.', {name: lastDecision.name})}
                    </p>
                    <h2 id="recorded-decision-title">{lastDecision.name}</h2>
                  </div>
                  <ApplicationStatusBadge status={lastDecision.accreditation_status} />
                </div>
                <DecisionHistory decisions={lastDecision.decisions} />
              </section>
            )}

            {decisionError && (
              <div className={'panel error ' + styles.errorPanel} role="alert">
                <p>{t('Decision request for {name}: {message}', {name: decisionError.orgName, message: decisionError.message})}</p>
                <button className="button button-secondary" type="button" onClick={applications.reload}>
                  {t('Refresh applications')}
                </button>
              </div>
            )}

            <section className={'panel ' + styles.applicationsPanel} aria-labelledby="applications-list-title">
              <header className={styles.sectionHeading}>
                <div>
                  <p className="eyebrow">{t('Platform administration')}</p>
                  <h2 id="applications-list-title">{t('Applications')}</h2>
                </div>
                <p className={styles.resultCount}>
                  {t('{shown} of {total} applications', {shown: visibleApplications.length, total: applicationList.length})}
                </p>
              </header>

              <div className={styles.filters}>
                <div className={styles.filterGroup} role="group" aria-label={t('Filter applications by status')}>
                  {statusFilters.map(filter => (
                    <button
                      key={filter.key}
                      className={styles.filterButton + (statusFilter === filter.key ? ' ' + styles.filterSelected : '')}
                      type="button"
                      aria-pressed={statusFilter === filter.key}
                      onClick={() => setStatusFilter(filter.key)}
                    >
                      {t(filter.label)} <span>({applicationCounts[filter.key]})</span>
                    </button>
                  ))}
                </div>
                <label className={styles.searchField} htmlFor="application-search">
                  <span>{t('Search applications')}</span>
                  <input
                    id="application-search"
                    type="search"
                    value={search}
                    onChange={event => setSearch(event.target.value)}
                    placeholder={t('Search by organization name or description')}
                  />
                </label>
              </div>

              {applications.loading && !applications.data && (
                <p className={styles.inlineFeedback} role="status">{t('Loading applications…')}</p>
              )}
              {applications.error && (
                <div className={'error panel ' + styles.inlineFeedback} role="alert">
                  <p>{t('Applications could not be loaded.')} {applications.error.message}</p>
                  <button className="button button-secondary" type="button" onClick={applications.reload}>
                    {t('Retry loading applications')}
                  </button>
                </div>
              )}
              {!applications.loading && !applications.error && !applications.data && (
                <p className={'empty-state ' + styles.inlineFeedback}>{t('No applications were returned by the service.')}</p>
              )}
              {applications.data && !applications.error && (
                applicationList.length === 0 ? (
                  <p className={'empty-state ' + styles.inlineFeedback}>{t('No applications were returned by the service.')}</p>
                ) : visibleApplications.length === 0 ? (
                  <p className={'empty-state ' + styles.inlineFeedback}>{t('No applications match the current search and status filter.')}</p>
                ) : (
                  <div className={styles.applicationGrid}>
                    {visibleApplications.map(application => (
                      <article className={styles.applicationCard} key={application.id}>
                        <header className={styles.applicationHeader}>
                          <div className={styles.organizationHeading}>
                            <h3>{application.name}</h3>
                            <p className={styles.submitted}>
                              {t('Submitted')} <time dateTime={application.created_at}>
                                {formatDate(application.created_at, preferences.language)} · {formatTime(application.created_at, preferences.language)} ({t('Manila time')})
                              </time>
                            </p>
                          </div>
                          <ApplicationStatusBadge status={application.accreditation_status} />
                        </header>
                        <p className={styles.description}>
                          {application.description || t('No description was provided.')}
                        </p>
                        <DecisionHistory decisions={application.decisions} />
                        {application.accreditation_status === 'pending' && (
                          <div className={styles.applicationActions}>
                            <button
                              className="button"
                              type="button"
                              disabled={workingOrgId !== null || applications.loading || Boolean(applications.error)}
                              onClick={() => setPendingDecision({application, outcome: 'approved'})}
                            >
                              {t('Approve after offline assessment')}
                            </button>
                            <button
                              className="button button-danger"
                              type="button"
                              disabled={workingOrgId !== null || applications.loading || Boolean(applications.error)}
                              onClick={() => setPendingDecision({application, outcome: 'rejected'})}
                            >
                              {t('Reject after offline assessment')}
                            </button>
                          </div>
                        )}
                      </article>
                    ))}
                  </div>
                )
              )}
            </section>

            <ModerationReportQueue key={'platform:' + token} token={token} />
            <AnnouncementReportQueue key={'announcements:' + token} token={token} />
          </>
        )}
      </div>

      <dialog
        ref={dialogRef}
        className={styles.confirmDialog}
        aria-labelledby="accreditation-confirmation-title"
        aria-describedby="accreditation-confirmation-description"
        onCancel={event => {
          event.preventDefault();
          setPendingDecision(null);
        }}
        onClose={() => setPendingDecision(null)}
      >
        {pendingDecision && (
          <div className={styles.dialogContent}>
            <p className="eyebrow">{t('Review accreditation decision')}</p>
            <h2 id="accreditation-confirmation-title">
              {pendingDecision.outcome === 'approved' ? t('Confirm approval') : t('Confirm rejection')}
            </h2>
            <p id="accreditation-confirmation-description">
              {t('You are about to record {outcome} for this organization.', {
                outcome: t(pendingDecision.outcome === 'approved' ? 'approval' : 'rejection'),
              })}
            </p>
            <div className={styles.confirmationSummary}>
              <strong>{pendingDecision.application.name}</strong>
              <ApplicationStatusBadge status={pendingDecision.application.accreditation_status} />
            </div>
            <p className={styles.muted}>
              {t('Approval or rejection closes this application review and cannot be changed here. Verify the offline assessment before continuing.')}
            </p>
            <div className={styles.dialogActions}>
              <button
                className="button button-secondary"
                type="button"
                autoFocus
                disabled={workingOrgId !== null}
                onClick={() => setPendingDecision(null)}
              >
                {t('Go back')}
              </button>
              <button
                className={pendingDecision.outcome === 'rejected' ? 'button button-danger' : 'button'}
                type="button"
                disabled={workingOrgId !== null}
                onClick={() => void decide(pendingDecision.application, pendingDecision.outcome)}
              >
                {workingOrgId === pendingDecision.application.id
                  ? t('Saving decision…')
                  : pendingDecision.outcome === 'approved'
                    ? t('Confirm approval')
                    : t('Confirm rejection')}
              </button>
            </div>
          </div>
        )}
      </dialog>
    </>
  );
}

export function OrganizationAdminPage() {
  const {version} = useSession();
  return <OrganizationAdminContent key={version} />;
}
