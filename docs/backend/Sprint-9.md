# Sprint 9 — desktop attendee polish and persistent preferences

Authorized 2026-10-16. Implement Sprint 9 only from the accepted Sprint 9–23
roadmap. Actual participant testing/review is deferred until the user requests it.
Preserve fictional local authentication, isolated PostgreSQL, all product access
and registration rules, approved PLM identity, and the four mobile tabs. No Penpot
writes, real OAuth, uploads, autosave, organizer redesign, or future-sprint features.

## Accepted direction and acceptance

- Desktop first: Discover, details/confirmation sheet, My Events, Chat, Profile,
  Settings, and shared attendee navigation. Primary 1440×900; also check 1280×720,
  1366×768, and 1920×1080. Maintain existing mobile functionality; dedicated mobile
  refinements belong to Sprint 11.
- Warm ivory/white, burgundy identity, navy actions, blue interaction, functional
  gold focus/selection; serif headings/event titles and sans interface text.
  Constrained ~680px feed, 72px header, 24px gutters, soft corners, airy spacing.
- Consistent interaction and loading/error/empty/success states, keyboard focus,
  usable sheets, meaningful feedback. Motion is optional and respects both app
  preferences and system reduced motion. Discovery decoration has pause/resume.
- Major layout changes require visual options and the user's choice. Existing
  approved structure may be polished independently while that choice is pending.
- Visual choice confirmed: A (Quiet heritage), expanded to use desktop side space.
  Main supplies contextual clubs/shortcuts and upcoming-registration sidebars from
  existing authorized APIs. Feed remains one readable ~680px column; discovery
  workspace may expand to 1440px. No invented calendar, ranking, saved events or
  announcements are introduced. Hide/reflow sidebars at narrower breakpoints.
- English default, Filipino option; light default, dark/system options; standard,
  large, extra-large text; high contrast, reduced motion, decoration pause.
- Signed-in preferences persist per account; guests persist per browser device.
  Account switching must not copy preferences or private UI from another account.
  No automatic guest-to-account overwrite. Failed saves retain retryable intent.
- Localize attendee interface, accessibility labels, state copy and operational
  errors, not organization/user-authored content. Existing management bodies are
  out of scope; shared shell text may be localized.

## Frozen preferences interface

GET/PATCH `/api/v1/me/preferences`, authenticated even for ineligible accounts.
Writable fields: `language: en|fil`, `theme: light|dark|system`,
`text_size: standard|large|extra_large`, `high_contrast: boolean`,
`reduced_motion: boolean`, `decoration_paused: boolean`.
Defaults: en, light, standard, false, false, false.
Read-only response: the six fields plus `initialized: boolean` and
`updated_at: UTC datetime|null`. GET without a row returns defaults, initialized
false, null timestamp; it does not write. PATCH rejects unknown/null values and
non-boolean boolean inputs. Partial atomic upsert preserves omitted fields;
empty PATCH is a read/no-op. Identity and privileges cannot be changed here.

Backend worker supplies `UserPreferences` in identity/preferences_models.py and
`router` in identity/preferences.py; main owns migration/import/router assembly.
Table `user_preferences`: user_id String(36) PK/FK users; six non-null fields with
the defaults above; updated_at UTC non-null. Check constraints for each enum.

Frontend worker supplies `PreferencesProvider`, `usePreferences` in
lib/preferences.tsx. Context: preferences, setPreference(key,value), resetPreferences,
status (loading/saving/saved/error), error, retry, isAccount, ready,
resolvedReducedMotion. Export Preferences type and DEFAULT_PREFERENCES.
Status/error must be accessible and account-scoped. Serialize saves; preserve
newer user edits and stale-response/account-switch guards.
HTML attributes: data-theme=light|dark (resolved), data-text-size matching enum,
data-high-contrast=true|false, data-reduced-motion=true|false. Root lang en|fil.
`useT()` from lib/i18n.ts returns `(English literal, optional values) => string`;
use `{name}` substitutions. Keep translated messages in lib/messages.ts. Unknown
literals fall back to English; in-scope visible copy must receive Filipino entries.

## Exclusive worker writes

1. Backend preferences: identity/preferences_models.py, identity/preferences.py,
   tests/identity/test_preferences.py only.
2. Preferences/localization: lib/preferences.tsx, lib/i18n.ts, lib/messages.ts,
   app/settings/page.tsx, features/preferences/* only.
3. Discovery/detail/registration: features/events/DiscoverFeed.tsx, EventDetail.tsx,
   features/registrations/RegistrationAction.tsx (if present), new dedicated
   features/events/attendee-events.module.css only. Request shared edits from main.
4. My Events/Chat/Profile: features/registrations/MyEvents.tsx,
   features/communication/Chat*.tsx, app/chat/page.tsx, app/profile/page.tsx,
   new dedicated attendee-pages.module.css only. Request shared edits from main.
5. QA: new Sprint 9 tests/browser harness and docs/validation/sprint9-quality-review.md
   only. Report production defects to main. Do not run database resets in parallel.

Main owns global CSS/tokens, shell/header, feedback/icons, session/API/date helpers,
layout provider wiring, migrations and model imports, shared communication styles,
other attendee localization, generated contracts, canonical reconciliation notes,
visual options, execution slots, and final acceptance. No commits or pushes by
workers. Preserve other workers' changes; never reset or delete their files.

## Required verification

Focused API tests against guarded scratch PostgreSQL: privacy/auth, defaults,
strict validation, partial writes, durability and concurrent omitted-field safety.
Browser checks: preference persistence across reload/sign-out/accounts; Filipino,
dark/system/contrast/larger text; reduced motion including OS; desktop fit; keyboard
sheet focus/escape/return; unchanged registration/waitlist/chat states and routes.
Use existing persisted local journeys rather than static outcomes. Run all DB
suites serially; meaningful regression checks and final static build/type/lint
checks. Document developer checks separately from deferred participant validation.

## Completion checkpoint — 2026-10-16

Implemented with six GPT-6 Luna/max workers and main-chat integration. Full serial
backend regression: 333 passed with five opt-in browser gates skipped; three new
migration/readiness checks also passed. All five opt-in browser suites passed in
serial runs, including the Sprint 9 preference, sidebar privacy, responsive and
chat overlap checks. Frontend tests 12/12, lint, TypeScript/static build and asset
credential guard passed. Applied mvp_0007 preserves existing fictional data.

See [acceptance record](../validation/sprint-9-acceptance-2026-10-16.md) and
[interaction handoff](../design/sprint9-interaction-handoff.md) for exact evidence
and limitations. Participant review remains deferred. No Sprint 10 feature,
Penpot write, deployment, commit or push was performed.
