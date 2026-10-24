# Sprint 16 — event banners and club logos

Authorized by "next sprint", 2026-10-19. Implement the accepted roadmap's local
media capability. Personal Google sign-in is verified; live PLM-account sign-in
remains a separate pending check. Media uses the existing fictional development
journeys for verification. No deployment or new cloud access is part of this sprint.

## Frozen contract

- JPEG, PNG and WebP only; maximum input 5 MiB and 12,000,000 decoded pixels.
  Inspect actual format, require matching image Content-Type, reject animation,
  truncated files and decompression bombs. Apply EXIF orientation, strip metadata,
  preserve aspect ratio, fit within 2048px, and encode a fresh static WebP.
- Accept a raw image request body (not multipart). Bound the streamed body even
  without Content-Length. Never trust filenames or accept remote URLs/SVG.
- Only current eligible owner/admin may write media. Pending organizations may
  prepare draft artwork and their logo; rejected organizations are read-only.
  Communication restrictions apply. Event media changes are draft-only.
- POST/DELETE `/api/v1/events/{event_id}/banner`, requiring a quoted current
  If-Match version (missing => 428; stale => 409). Lock organization then event,
  recheck permission, and update the draft's content version with the media ID.
- POST/DELETE `/api/v1/organizations/{org_id}/logo` under the organization lock.
- All four mutations return MediaMutationOut:
  `{media_url: string|null, width: int|null, height: int|null,
  byte_size: int|null, draft_version: string|null}`. DELETE is idempotent when
  already empty. Media URLs are relative `/api/v1/media/{uuid}` only.
- EventPublic/EventPrivate add nullable `banner_url`; OrganizationOut adds
  nullable `logo_url`. Event.banner_media_id and Organization.logo_media_id are
  nullable string UUID references. MediaAsset has id, org_id, kind ('banner' or
  'logo'), width, height, byte_size, created_by, created_at. Stored filename is
  generated UUID + `.webp`, never user input. Retain existing fixture banner keys
  as the fallback; attaching a banner to an empty theme sets 'heritage' so existing
  publishing constraints remain valid. Removing an upload restores that fallback.
- GET `/api/v1/media/{media_id}` resolves current attachment and checks access
  every time: published approved-organization banners and approved logos are
  public; draft/pending content is eligible owner/admin only. Detached/replaced
  assets return 404. There is no static mount of the media root. Return image/webp,
  nosniff and private/no-store responses. Missing files return a controlled 404.
- Files persist under a configured absolute local media root, defaulting to
  Backend/.local/media/{fixture|real}/{local|test}. Test fixtures override the root
  to their owned temporary directory. Config must prohibit sharing a real root
  with fixture/test data. Generated assets are ignored by Git. Atomic file writes
  precede DB attachment; a DB rollback must never alter the previous file. Detached
  files are inaccessible and retained for later explicit storage reconciliation.

## Ownership

Coordinator owns existing backend config/domain models/schemas/projections,
router assembly, migration mvp_0011_media, dependencies/locks, shared API helper,
generated frontend types/i18n assembly, workspace logo integration and runtime,
database/browser verification, documentation and canonical notes.

Backend worker owns only new app/domains/media/** and tests/media/test_codec.py.
Frontend worker owns new features/media/**, tests/sprint16-media*.test.mjs,
and existing features/events/DraftEditor.tsx and app/event-artwork.tsx.
QA worker owns tests/media/test_access.py and docs/validation/sprint16-quality-review.md.
Workers do not run DB/browser tests or change another owner's files.

Shared frontend api() will accept Blob bodies, infer Content-Type, and support
responseType:'blob'. Existing origin/token guards apply. MediaUploader props:
endpoint, token, ifMatch?, disabled?, currentUrl?, onChanged(MediaMutationOut).
MediaImage props: mediaUrl, alt, token?, className?. It fetches protected bytes
using api<Blob>(relativePath, {token,responseType:'blob',signal}), creates a local
object URL, and clears it on account/URL changes and unmount. No bearer query
strings. Include localized accessible selection/upload/remove/loading/error states.
Draft uploads require a saved draft with no pending changes; update the editor's
draft_version and saved snapshot after a media mutation without erasing edits.
Organizer management remains desktop-only; public banners/logos render on mobile.

## Acceptance

Verify valid uploads, metadata removal/orientation, MIME spoofing/corrupt/animated/
oversized/dimension-limit rejection, guest/private/cross-org/role/rejected-org
access, draft version conflicts, published-edit denial, replacement/removal,
rollback preservation and restart persistence. Exercise existing publish and feed
paths with uploaded banners and fixture fallback. Preserve all existing data via
reviewed additive migration; record pre/post table counts in both local databases.
Run scratch PostgreSQL suites serially. Check desktop/mobile views and actual
file upload in the local fictional browser journey. Document what was observed;
participant validation and live PLM account verification remain separate gates.
