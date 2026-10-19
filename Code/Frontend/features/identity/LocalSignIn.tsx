'use client';

import { useState, useSyncExternalStore } from 'react';
import { ApiError, localDemoEnabled } from '@/lib/api';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { DemoAccount } from '@/lib/types';
import { useT } from '@/lib/i18n';

const subscribeToLocalDemo = () => () => {};
const serverLocalDemoEnabled = () => false;

function visibleError(error: ApiError): string {
  if (error.status === 401 || error.status === 403) {
    return 'Your local sign-in could not be verified. Choose a fictional account and retry.';
  }
  if (error.status === 404) {
    return 'The local fictional-account catalog is unavailable. Check the local backend, then retry.';
  }
  return error.message;
}

export function LocalSignIn() {
  const { actor, label, authLoading, error: sessionError, selectAccount, signOut } = useSession();
  const t = useT();
  const demoAvailable = useSyncExternalStore(subscribeToLocalDemo, localDemoEnabled, serverLocalDemoEnabled);
  const catalog = useApiResource<DemoAccount[]>(demoAvailable ? '/local-demo/accounts' : null);
  const accounts = catalog.data ?? [];
  const [selectedLabel, setSelectedLabel] = useState('');
  const [attemptedAccount, setAttemptedAccount] = useState<DemoAccount | null>(null);

  const selectedAccount = accounts.find(account => account.label === selectedLabel) ?? null;

  async function continueWithAccount() {
    if (!selectedAccount) return;
    setAttemptedAccount(selectedAccount);
    await selectAccount(selectedAccount);
  }

  return <>
    {demoAvailable && <span className="status-chip">{t('Not real sign-in')}</span>}
    {demoAvailable && <label>
      <span>{t('Choose a fictional account')}</span>
      <select
        aria-label={t('Choose a fictional local account')}
        value={selectedLabel}
        disabled={catalog.loading || accounts.length === 0}
        onChange={event => setSelectedLabel(event.target.value)}
      >
        <option value="">{t('Select an account')}</option>
        {accounts.map(account => <option key={account.label} value={account.label}>{account.label}</option>)}
      </select>
    </label>}
    {catalog.loading && <span role="status">{t('Loading fictional accounts…')}</span>}
    {demoAvailable && !catalog.loading && !catalog.error && accounts.length === 0 &&
      <span role="status">{t('No fictional accounts are available.')}</span>}
    {catalog.error && <span role="alert" className="error">
      {t(visibleError(catalog.error))}{' '}
      <button className="button button-secondary" type="button" onClick={catalog.reload}>
        {t('Retry')}
      </button>
    </span>}
    {demoAvailable && <button
      className="button"
      type="button"
      disabled={!selectedAccount || catalog.loading || authLoading}
      onClick={() => void continueWithAccount()}
    >
      {authLoading ? t('Checking local account…') : t('Use fictional account')}
    </button>}
    {actor && <span role="status" className="status-chip">{t('Local session: {label}', {label:label ?? actor.nickname ?? t('active')})}</span>}
    {sessionError && <span role="alert" className="error">
      {t(visibleError(sessionError))}{' '}
      {attemptedAccount && <button className="button button-secondary" type="button"
        disabled={authLoading} onClick={() => void selectAccount(attemptedAccount)}>{t('Retry')}</button>}
    </span>}
    <button className="button button-secondary" type="button" onClick={() => {
      setAttemptedAccount(null);
      signOut();
    }}>
      {t('Continue as guest')}
    </button>
  </>;
}
