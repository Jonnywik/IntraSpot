'use client';

import { usePreferences } from '@/lib/preferences';
import { useT } from '@/lib/i18n';

export function HeritageDecoration() {
  const { preferences, setPreference, resolvedReducedMotion } = usePreferences();
  const t = useT();
  return <aside className="heritage-aside" data-paused={preferences.decoration_paused || resolvedReducedMotion} aria-label={t('Heritage decoration')}>
    <svg viewBox="0 0 100 110" fill="none" stroke="currentColor" strokeWidth="1.2" className="heritage-decoration" aria-hidden="true">
      <path d="M14 105V58Q14 27 50 10Q86 27 86 58V105M24 105V59Q24 35 50 20Q76 35 76 59V105M34 105V61Q34 44 50 32Q66 44 66 61V105M6 106H94M8 57H25M75 57H92" />
      <g className="heritage-foliage"><path d="M2 101Q12 83 3 68M98 101Q89 84 97 67M1 88L12 82M88 82L99 87M6 75L12 71M89 71L96 76" /></g>
    </svg>
    <button type="button" className="text-action decoration-control" disabled={resolvedReducedMotion}
      aria-pressed={preferences.decoration_paused || resolvedReducedMotion}
      onClick={() => setPreference('decoration_paused', !preferences.decoration_paused)}>
      {resolvedReducedMotion ? t('Decoration is static') : preferences.decoration_paused ? t('Resume decoration') : t('Pause decoration')}
    </button>
  </aside>;
}
