# Sprint 24 accessibility sidecar review

## Scope and method

Read-only source review of `Code/Frontend/app/site-header.tsx`, `Code/Frontend/app/settings/page.tsx`, `Code/Frontend/lib/preferences.tsx`, and `Code/Frontend/app/globals.css`, plus the immediately related layout, active stylesheets, translation lookup, and Settings styles. No browser, database, build, dependency, or Git operations were run. This review is separate from the coordinator's isolated browser gates and does not perform fixes or integration.

## Findings

### 1. The skip link has no explicitly focusable destination

`Code/Frontend/app/site-header.tsx:41` links to `#main-content`. Its target is `Code/Frontend/components/application-shell.tsx:13`, where `<main id="main-content">` has no `tabIndex`. The source therefore does not make the destination focusable for the keyboard user after activating the skip link.

**Minimal fix:** add `tabIndex={-1}` to the main landmark so the skip link can move focus to the content.

### 2. “Discover” stays English when Filipino is selected

`Code/Frontend/app/site-header.tsx:12,37-39` passes the `Discover` label through `t()`. `Code/Frontend/lib/i18n.ts:27-29,37-40` builds the Filipino lookup and returns the original English string when a key is absent. An exact-key search across `Code/Frontend` found no Filipino `Discover` entry, so both rendered navigation copies retain that English label.

**Minimal fix:** add a `Discover` translation, such as `Tuklasin`, to a dictionary included in `filipinoMessages`.

## Areas checked

- **Header and mobile-tab invariants:** `Code/Frontend/app/site-header.tsx:11-16,37-54` defines four links once, renders the same entries in desktop and mobile navigation, marks the current route, provides translated navigation names, and gives the icon-only Notifications and Profile links accessible names. `Code/Frontend/app/mobile.css:22-42` keeps four equal columns and permits labels to wrap; `Code/Frontend/app/site-header.tsx:23-35` measures nav height, and `Code/Frontend/app/mobile.css:2-8` uses that height for content clearance.
- **Settings labels and grouping:** `Code/Frontend/app/settings/page.tsx:50-103` associates the language select with a label and groups theme/text-size radios with fieldsets and legends. Lines `106-149` wrap accessibility and decoration checkboxes in labels and expose the static-decoration status. Loading, saving, success, and error feedback use status or alert roles at lines `38-48`.
- **Preference application:** `Code/Frontend/lib/preferences.tsx:16-23,438-457,467-476` defines language and all three text-size values, observes the device reduced-motion preference, combines it with the saved choice, and applies language, text size, contrast, and motion state to the document root.
- **Active style order and focus/motion rules:** `Code/Frontend/app/layout.tsx:3-5` loads `globals.css`, then `foundations.css`, then `mobile.css`. The active foundation rules set standard/large/extra-large root sizes and visible keyboard outlines at `Code/Frontend/app/foundations.css:22-37`; reduced-motion rules disable animation, transitions, scrolling motion, and hover transforms at lines `168-173`. Mobile navigation has an inset visible focus outline at `Code/Frontend/app/mobile.css:50-52`.
- **Larger-text and wrapping source paths:** `Code/Frontend/app/foundations.css:22-25,159` uses root-relative text sizing for mobile tab labels. `Code/Frontend/app/mobile.css:30-42` allows translated labels to wrap within each of the four grid cells. `Code/Frontend/features/preferences/preferences.module.css:68-99,120-149,186-195` permits Settings choices and supporting copy to wrap and collapses the choice grid on narrow widths.

## Evidence limits and open validation

This is source evidence only. It does not establish rendered focus transfer, actual Filipino or extra-large-text wrapping at specific viewport sizes, browser zoom behavior, screen-reader announcements, or reduced-motion behavior in a running app. No physical-device or participant validation was performed; those limits remain open. The main coordinator owns the isolated browser gates and all fixes/integration.

## Coordinator follow-up

The coordinator reproduced both findings in Edge, then fixed the main landmark's
focusability and the missing translation. The new isolated matrix passed all
52 checks: six attendee routes at six viewport sizes, combined Filipino,
extra-large text/dark/high contrast, four mobile tabs and bottom clearance,
actual `MAIN#main-content` focus and reduced motion. The worker's source review
is distinct from that execution. See the [Sprint 24 acceptance record](sprint-24-acceptance-2026-10-24.md)
and its selected evidence. Physical devices, screen-reader audits and participant
studies remain unperformed.
