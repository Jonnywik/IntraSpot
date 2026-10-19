'use client';

import Link from 'next/link';
import { DiscoveryPreferences } from '@/features/preferences/DiscoveryPreferences';
import { useT } from '@/lib/i18n';
import { usePreferences, type Preferences } from '@/lib/preferences';
import styles from '@/features/preferences/preferences.module.css';

export default function SettingsPage() {
  const t = useT();
  const {
    preferences,
    setPreference,
    resetPreferences,
    status,
    error,
    retry,
    isAccount,
    ready,
    resolvedReducedMotion,
  } = usePreferences();

  return <>
    <header className={`page-heading ${styles.header}`}>
      <p className="eyebrow">{t('Preferences')}</p>
      <h1>{t('Settings')}</h1>
      <p className="muted">{t('Choose how IntraSpot looks and feels. Your choices apply immediately.')}</p>
      <Link className="button button-secondary" href="/organizations">{t('Clubs and membership')}</Link>
    </header>

    <section
      className={`panel stack ${styles.panel}`}
      aria-labelledby="settings-preferences-heading"
      aria-busy={!ready}
    >
      <h2 id="settings-preferences-heading" className={styles.visuallyHidden}>{t('Preferences')}</h2>

      {status === 'loading' ? <p className={styles.feedback} role="status">{t('Loading preferences…')}</p> : null}
      {status === 'saving' ? <p className={styles.feedback} role="status" aria-live="polite">{t('Saving preferences…')}</p> : null}
      {status === 'saved' ? <p className={styles.feedback} role="status" aria-live="polite">{t('Preferences saved.')}</p> : null}
      {error ? (
        <div className={styles.errorActions}>
          <p className={`error ${styles.feedback}`} role="alert">{t(error)}</p>
          <button className="button button-secondary" type="button" onClick={retry} disabled={!ready}>
            {t('Retry')}
          </button>
        </div>
      ) : null}

      <section className={styles.section} aria-labelledby="settings-display-heading">
        <h2 id="settings-display-heading" className={styles.sectionHeading}>{t('Display')}</h2>
        <label className={styles.selectField} htmlFor="settings-language">
          <span>{t('Language')}</span>
          <select
            id="settings-language"
            value={preferences.language}
            disabled={!ready}
            onChange={event => setPreference('language', event.currentTarget.value as Preferences['language'])}
          >
            <option value="en">{t('English')}</option>
            <option value="fil">{t('Filipino')}</option>
          </select>
        </label>

        <fieldset className={styles.choiceGrid} disabled={!ready}>
          <legend>{t('Theme')}</legend>
          {([
            ['light', 'Light'],
            ['dark', 'Dark'],
            ['system', 'Use your device setting'],
          ] as const).map(([value, label]) => (
            <label className={styles.choice} key={value}>
              <input
                type="radio"
                name="settings-theme"
                value={value}
                checked={preferences.theme === value}
                onChange={() => setPreference('theme', value)}
              />
              <span>{t(label)}</span>
            </label>
          ))}
        </fieldset>

        <fieldset className={styles.choiceGrid} disabled={!ready}>
          <legend>{t('Text size')}</legend>
          {([
            ['standard', 'Standard'],
            ['large', 'Large'],
            ['extra_large', 'Extra large'],
          ] as const).map(([value, label]) => (
            <label className={styles.choice} key={value}>
              <input
                type="radio"
                name="settings-text-size"
                value={value}
                checked={preferences.text_size === value}
                onChange={() => setPreference('text_size', value)}
              />
              <span>{t(label)}</span>
            </label>
          ))}
        </fieldset>
      </section>

      <section className={styles.section} aria-labelledby="settings-accessibility-heading">
        <h2 id="settings-accessibility-heading" className={styles.sectionHeading}>{t('Accessibility')}</h2>
        <div className={styles.toggleList}>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={preferences.high_contrast}
              disabled={!ready}
              onChange={event => setPreference('high_contrast', event.currentTarget.checked)}
            />
            <span className={styles.toggleCopy}>
              <strong>{t('High contrast')}</strong>
              <span>{t('Increase contrast between text, controls, and their backgrounds.')}</span>
            </span>
          </label>
          <label className={styles.toggle}>
            <input
              type="checkbox"
              checked={preferences.reduced_motion}
              disabled={!ready}
              onChange={event => setPreference('reduced_motion', event.currentTarget.checked)}
            />
            <span className={styles.toggleCopy}>
              <strong>{t('Reduce motion')}</strong>
              <span>{t("Limit interface animation and transitions. Your device's reduced-motion setting is always honored.")}</span>
            </span>
          </label>
        </div>
      </section>

      <section className={styles.section} aria-labelledby="settings-decoration-heading">
        <h2 id="settings-decoration-heading" className={styles.sectionHeading}>{t('Heritage decoration')}</h2>
        <label className={styles.toggle}>
          <input
            type="checkbox"
            checked={preferences.decoration_paused}
            disabled={!ready}
            onChange={event => setPreference('decoration_paused', event.currentTarget.checked)}
          />
          <span className={styles.toggleCopy}>
            <strong>{t('Pause decoration')}</strong>
          </span>
        </label>
        {resolvedReducedMotion ? <p className={styles.sectionDescription} role="status">{t('Decoration is static')}</p> : null}
      </section>

      <div className={styles.errorActions}>
        {ready && status === 'saved' && !error ? (
          <p className={styles.accountNote} role="status">
            {t(isAccount ? 'These preferences are saved for this account.' : 'These preferences are saved on this browser device.')}
          </p>
        ) : null}
        <button className="button button-secondary" type="button" onClick={resetPreferences} disabled={!ready}>
          {t('Reset to defaults')}
        </button>
      </div>
    </section>
    <DiscoveryPreferences />
  </>;
}
