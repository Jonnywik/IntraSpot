# Sprint 16 quality review

**Status:** Worker review complete; coordinator verification recorded separately, 2026-10-19

**Contract:** `docs/backend/Sprint-16.md` (frozen shared contract)

## Review scope

This review is limited to the media API, ownership and authorization boundaries,
attachment replacement/removal, private and public reads, streamed input limits,
and rollback behavior. The assigned API coverage is in
`Code/Backend/tests/media/test_access.py`.

The tests replace `get_settings().media_root` with pytest's `tmp_path` using
`monkeypatch`; pytest restores the setting after each test. Uploads therefore do
not target a configured development media directory.

## Implementation review

The shared event model, media-root setting, event projections, router assembly,
media backend, and frontend integration are present and were inspected. The
backend rechecks manager access while holding organization/event locks, uses
generated immutable media IDs, and resolves reads only while an asset remains
attached. Pending or draft media requires manager access; only approved
organization logos and approved published-event banners are public. The
frontend fetches images through the API with bearer auth in headers and revokes
temporary object URLs on cleanup.

The main focused run exposed these defects; fixes are present in the current
working tree:

- The Windows upload 500 was caused by `os.link()` failing with permission
  denied (`errno 13` / `winerror 5`), not by the foreign key. Storage now
  reserves a unique destination with exclusive creation and atomically replaces
  that empty reservation with the complete temporary file. Main reports the
  storage probe passes; `test_storage.py` now covers UUID collisions and failed
  installation without damaging an existing file.
- Image normalization now uses Pillow's non-upscaling thumbnail operation, so
  small source images are not enlarged to the output edge limit.
- The `MediaAsset` row is also flushed before its ID is assigned to the event or
  organization pointer, preserving the foreign-key ordering.

The banner-upload/autosave race was also reviewed. Both operations change the
draft version, so overlap could make one request stale. The current editor sets
a synchronous media-busy ref and blocks autosave, field edits, reload, and
publish until the media request settles; the controls are disabled as well.
The worker did not exercise the browser. The coordinator subsequently observed
disabled draft controls during upload and a saved, loaded private preview; see
the final acceptance report for the exact evidence boundary.

One remaining storage-hygiene concern is separate from preserving the old
attachment: if the file install succeeds and the database commit later fails,
the rollback restores the old database pointer but leaves the newly installed
UUID file unreferenced. Repeated commit failures can accumulate files. The
current rollback test checks old-pointer/file preservation, not orphan cleanup;
consider a cleanup/reconciliation path if that failure mode is in scope.

Main reports 25 passing and 1 failing focused checks. The remaining failure was
the rollback test expecting a raised `RuntimeError`; request middleware instead
returns a controlled 500. That test now asserts the 500 response and retains
its database-pointer and previous-file preservation assertions. Expected-
success upload assertions include JSON response details to expose any remaining
machine-readable API error.

## API coverage prepared

- Ineligible personal owners, cross-organization users, and moderators cannot
  write; eligible admins can.
- Pending organizations may prepare private draft banners and logos. Rejected
  organizations and published events reject media changes.
- Event banner writes require the current quoted `If-Match`; stale writes leave
  the current attachment intact.
- Draft and pending media are not guest-readable. Approved published banners
  and logos are publicly readable through the media endpoint.
- Replaced and detached media become inaccessible; repeated removal is safe and
  event theme fallback remains available.
- Missing files return a controlled not-found response. A failed database
  commit during replacement preserves the prior attachment and file.
- MIME spoofing and a streamed body over 5 MiB without `Content-Length` are
  rejected. Pending personal-review restrictions block writes.

## Verification status

The database and browser suites have not been run by this QA worker, as required
by the sprint contract. No additional concrete critical security, race, or
ownership bug was found in the current source review. The unreferenced-file
case above is a non-critical storage-growth concern. The coordinator's serial
PostgreSQL and browser results are recorded in
`docs/validation/sprint-16-acceptance-2026-10-19.md`; they supersede the preliminary
run counts above. Unreferenced files remain deliberately inaccessible and retained
for later explicit reconciliation under the frozen local-only contract. Before
hosting or accepting untrusted production traffic, resolve storage quotas,
reconciliation and operational abuse controls.
