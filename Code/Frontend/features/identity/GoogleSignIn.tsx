'use client';

import { useState, useSyncExternalStore } from 'react';
import { useSession } from '@/lib/session';
import { useT } from '@/lib/i18n';
import { getRealAuthConfig } from '@/lib/supabase-auth';
import styles from './google-sign-in.module.css';

const subscribeToAuthConfig = () => () => {};
const serverAuthConfigured = () => false;

function browserAuthConfigured(): boolean {
  return typeof window !== 'undefined' && Boolean(getRealAuthConfig());
}

export function GoogleSignIn() {
  const { actor, token, authLoading, error, signInWithGoogle, signOut, refreshActor } = useSession();
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [startFailed, setStartFailed] = useState(false);
  const sessionVerified = Boolean(actor && !authLoading && !error);
  const verificationFailed = Boolean(!authLoading && error && (token || error.status === 401));
  const available = useSyncExternalStore(
    subscribeToAuthConfig,
    browserAuthConfigured,
    serverAuthConfigured,
  );

  async function startSignIn() {
    setBusy(true);
    setStartFailed(false);
    try {
      await signInWithGoogle();
    } catch {
      setStartFailed(true);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.controls}>
      {authLoading && <span role="status">{t(token ? 'Verifying account with the local IntraSpot API…' : 'Checking development session…')}</span>}
      {sessionVerified && <span role="status" className={styles.sessionStatus}>{t('IntraSpot session verified.')}</span>}
      {verificationFailed && <span role="status">{t('Local account verification failed. Sign in again or retry local verification.')}</span>}
      {sessionVerified && actor && (
        <span role="status">{t(actor.eligible ? 'PLM email eligibility confirmed.' : 'Not eligible for PLM-only actions.')}</span>
      )}
      {token ? (
        <>
          <button className="button button-secondary" type="button" onClick={signOut}>
            {t('Sign out')}
          </button>
        </>
      ) : (
        <button
          className="button"
          type="button"
          disabled={!available || authLoading || busy}
          onClick={() => void startSignIn()}
        >
          {busy ? t('Checking development session…') : t('Continue with Google')}
        </button>
      )}
      {!available && <span role="status">{t('Google sign-in is available only in the configured isolated development profile.')}</span>}
      {(error || startFailed) && (
        <span role="alert" className="error">
          {t(error?.message ?? 'Google sign-in could not be started. Retry.')}
        </span>
      )}
      {token && error && (
        <button className="button button-secondary" type="button" onClick={() => void refreshActor()}>
          {t('Retry local verification')}
        </button>
      )}
      <details className={styles.details}>
        <summary>{t('About development sign-in')}</summary>
        <div className={styles.explanation}>
          <p>{t('Development-only Google sign-in. This profile uses a separate local API and Supabase Auth project.')}</p>
          {actor?.eligible === false && (
            <p>{t('Your Google account can browse public events. PLM-only actions require an eligible PLM account.')}</p>
          )}
          {actor && !actor.profile_complete && <p>{t('Complete your profile before registering.')}</p>}
          <p>{t('No admin access or organization memberships are granted automatically.')}</p>
          <p>{t('This tab keeps session credentials in memory. Reloading requires another sign-in.')}</p>
        </div>
      </details>
    </div>
  );
}
