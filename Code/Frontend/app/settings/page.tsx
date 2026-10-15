'use client';

import { useState } from 'react';
import Link from 'next/link';

type TextSize = 'normal' | 'large';

function readRootSettings() {
  if (typeof document === 'undefined') return { reduceMotion: false, textSize: 'normal' as TextSize };
  const root = document.documentElement;
  return {
    reduceMotion: root.dataset.reducedMotion === 'true',
    textSize: root.dataset.textSize === 'large' ? 'large' as const : 'normal' as const,
  };
}

export default function SettingsPage() {
  const [settings, setSettings] = useState(readRootSettings);

  function changeMotion(value: boolean) {
    setSettings(current => ({ ...current, reduceMotion: value }));
    if (value) document.documentElement.dataset.reducedMotion = 'true';
    else delete document.documentElement.dataset.reducedMotion;
  }

  function changeTextSize(value: TextSize) {
    setSettings(current => ({ ...current, textSize: value }));
    if (value === 'large') document.documentElement.dataset.textSize = 'large';
    else delete document.documentElement.dataset.textSize;
  }

  return <>
    <header className="page-heading">
      <p className="eyebrow">Preferences</p>
      <h1>Settings</h1>
      <p className="muted">Adjust motion and text size for readability.</p>
      <Link className="button button-secondary" href="/organizations">Clubs and membership</Link>
    </header>
    <section className="panel stack" aria-label="Accessibility settings">
      <div className="stack">
        <h2>Motion</h2>
        <p className="muted">Reduce animation and transitions across IntraSpot.</p>
        <label className="actions">
          <input
            type="checkbox"
            checked={settings.reduceMotion}
            onChange={event => changeMotion(event.target.checked)}
          />
          <span>Reduce motion</span>
        </label>
      </div>
      <fieldset className="stack">
        <legend>Text size</legend>
        <label className="actions">
          <input
            type="radio"
            name="text-size"
            value="normal"
            checked={settings.textSize === 'normal'}
            onChange={() => changeTextSize('normal')}
          />
          <span>Standard</span>
        </label>
        <label className="actions">
          <input
            type="radio"
            name="text-size"
            value="large"
            checked={settings.textSize === 'large'}
            onChange={() => changeTextSize('large')}
          />
          <span>Large</span>
        </label>
      </fieldset>
      <p role="status" className="muted">
        Changes apply immediately and stay in this tab. They are not saved to an account and reset on reload.
      </p>
    </section>
  </>;
}
