# Sprint 16 — media interaction handoff

Local application implementation, 2026-10-19. No Penpot synchronization or
redesign. Preserve Quiet Heritage colors, typography, existing event crops,
responsive cards, and the four attendee destinations.

## Authoring

- The saved event-draft editor adds a labeled image picker, format/size guidance,
  Upload/Replace, and Remove. Club-logo controls appear in the existing authorized
  desktop organization workspace. Pending organizations may prepare; rejected
  organizations are read-only. Moderators do not gain authoring controls.
- Support JPEG/PNG/WebP up to 5 MiB and 12 megapixels. The server remains
  authoritative: inspect decoded content, normalize orientation, strip metadata,
  encode static WebP, preserve aspect ratio, and never upscale.
- File selection does not upload automatically. Keep an explicit action; expose
  progress, success, validation, permission, storage, and retry feedback through
  accessible status text. Disable unsupported or busy actions honestly.
- Event upload/removal requires an already saved, unchanged draft and its latest
  version. While a media mutation runs, block field edits, autosave, reload, and
  publishing synchronously as well as disabling their controls. Adopt the returned
  draft version without overwriting the saved form. A stale/missing version asks
  the author to review/reload rather than silently overwriting another change.
- An uploaded banner takes priority over the fixture theme. Removal restores the
  selected theme fallback; it does not erase unrelated event fields. Publishing
  and approval rules remain unchanged; published artwork cannot be edited here.

## Reading and privacy

- Public event cards/details and club-directory cards render the attached image
  using existing responsive styling. No crop editor or personal photos were added.
- Only approved organization logos and published approved-organization event
  banners are public. Private draft/pending previews require a current authorized
  manager. Replaced/detached images are no longer retrievable by their old URL.
- Fetch only relative API media paths. Bearer credentials travel in headers,
  never image URLs. Convert authorized bytes to a temporary browser object URL;
  clear/revoke it when the account, image, or component changes. Do not carry a
  previous private preview into another account's view.
- Mobile remains attendee-facing. Display public media without introducing mobile
  organization-management screens or changing Discover/My Events/Chat/Settings.

## Observed and deferred

Actual browser checks exercised an existing approved fictional club's logo,
an existing pending organization's private draft banner, disabled edits during
upload, success/removal, API restart persistence, and anonymous club display at
390×844 without horizontal overflow. The temporary attachments were removed and
the draft's original empty theme restored afterward. Screenshots are in the
[acceptance report](../validation/sprint-16-acceptance-2026-10-19.md).

Published uploaded-banner access and invalid/unauthorized cases are PostgreSQL
API-test evidence, not an actual browser publication demonstration. Real PLM
sign-in, physical-device and participant validation remain separate checks.
