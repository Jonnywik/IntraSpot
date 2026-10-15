'use client';

import { useState, useSyncExternalStore } from 'react';
import { ApiError, localDemoEnabled } from '@/lib/api';
import { useSession } from '@/lib/session';
import { useApiResource } from '@/lib/use-api-resource';
import type { DemoAccount } from '@/lib/types';

const subscribeToLocalDemo = () => () => {};
const serverLocalDemoEnabled = () => false;

function visibleError(error: ApiError): string {
  if (error.status === 401 || error.status === 403) {
    return `Access denied (${error.status}). ${error.message}`;
  }
  if (error.status === 404) {
    return `The local fictional-account catalog is unavailable. ${error.message}`;
  }
  return error.message;
}

export function LocalSignIn() {
  const { actor, label, authLoading, error: sessionError, selectAccount, signOut } = useSession();
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
    {demoAvailable && <span className="status-chip">Not real sign-in</span>}
    {demoAvailable && <label>
      <span>Choose a fictional account</span>
      <select
        aria-label="Choose a fictional local account"
        value={selectedLabel}
        disabled={catalog.loading || accounts.length === 0}
        onChange={event => setSelectedLabel(event.target.value)}
      >
        <option value="">Select an account</option>
        {accounts.map(account => <option key={account.label} value={account.label}>{account.label}</option>)}
      </select>
    </label>}
    {catalog.loading && <span role="status">Loading fictional accounts…</span>}
    {demoAvailable && !catalog.loading && !catalog.error && accounts.length === 0 &&
      <span role="status">No fictional accounts are available.</span>}
    {catalog.error && <span role="alert" className="error">
      {visibleError(catalog.error)}{' '}
      <button className="button button-secondary" type="button" onClick={catalog.reload}>
        Retry
      </button>
    </span>}
    {demoAvailable && <button
      className="button"
      type="button"
      disabled={!selectedAccount || catalog.loading || authLoading}
      onClick={() => void continueWithAccount()}
    >
      {authLoading ? 'Checking local account…' : 'Use fictional account'}
    </button>}
    {actor && <span role="status" className="status-chip">Local session: {label ?? actor.nickname ?? 'active'}</span>}
    {sessionError && <span role="alert" className="error">
      {visibleError(sessionError)}{' '}
      {attemptedAccount && <button className="button button-secondary" type="button"
        disabled={authLoading} onClick={() => void selectAccount(attemptedAccount)}>Retry</button>}
    </span>}
    <button className="button button-secondary" type="button" onClick={() => {
      setAttemptedAccount(null);
      signOut();
    }}>
      Continue as guest
    </button>
  </>;
}
