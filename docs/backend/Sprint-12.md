# Sprint 12 — explainable For You discovery

Authorized 2026-10-17. Canonical Implementation Roadmap and UI & UX own scope.
Preserve Sprint 9–11 code/data, PLM styling, mobile four tabs and all access rules.
No cloud, GPS, external calendar, Flash (Sprint 13), deployment or Git commit.

## Frozen contracts

- API `GET /events` adds `sort=for_you`; API omitted sort remains `upcoming` for
  backward compatibility. Signed-in UI defaults to For You; guests use Upcoming.
  Guest `for_you` falls back to Upcoming without personalized reasons.
- Server globally ranks BEFORE limit/offset, not just the first page: active
  eligible club membership first, then number of distinct exact normalized
  interest-tag matches, area match, whole-event availability fit; finally
  starts_at/id ascending. Explicit Upcoming/Newest retain existing order and
  have no personalized reasons. Search and My Clubs compose with every sort.
- Event optional metadata: `tags: string[]` (max 16, each 1–64),
  `coarse_area: string|null` (max 80, blank clears). Normalize labels with NFKC,
  whitespace collapse and casefold; tags deduplicate. Existing rows get []/null.
  Draft/preview support metadata; no new publishing requirement. Published
  metadata stays immutable under the existing published-edit policy. Draft
  content versions include both fields. No title/address/tag inference.
- `EventPublic` adds those metadata fields and
  `recommendation_reasons: ('club'|'interests'|'area'|'availability')[]` default [].
  For You emits only matched controlled reason codes, in that order, to the
  requesting account. Never echo private tags, area or availability as reasons.
  Public detail/guest/explicit chronology projections have no personalized codes.
- Separate private API GET/PATCH `/me/discovery-preferences` (any verified account):
  `{coarse_area: string|null, availability: AvailabilityWindow[], updated_at}`.
  PATCH is partial; null area or [] windows clear. Defaults null/[], no row needed.
  Unknown fields/types invalid; user_id always derived from the token.
- `AvailabilityWindow = {weekday: int 0..6, start_minute: int 0..1439,
  end_minute: int 1..1440}`; Monday=0, end > start, max 28 rows. Weekly Manila
  windows, not calendar dates. Explain overnight as two adjacent-day rows. Merge
  overlapping/adjacent intervals for fit, including Sunday→Monday continuity.
  A fit requires the entire event, not just its start; exact end is inclusive.
  Full-week coverage permits multiweek events; otherwise a >week event cannot fit.
  Neither preference is required to browse/register. User tags reuse private
  profile interests, not duplicated discovery data.
- Named-area text is an implementation choice, not a venue directory or precise
  location signal. UI asks for a broad named area, not a street address. Matching
  uses normalized equality. Users can change/clear values in Settings.
- Server metadata and preference shape/model names:
  `Event.tags`, `Event.coarse_area`; `UserDiscoveryPreferences` in
  `identity/discovery_models.py` with user_id/coarse_area/availability/updated_at.
  Shared normalization/window types live in `app/core/discovery.py`.

## Ownership and integration

Coordinator: shared helpers/models, additive `mvp_0008`, router assembly, seed
integration, schema/type exports, translations, migration/cross-domain tests,
serial verification and handoff. Five non-overlapping Luna/max workers:
identity discovery API; event ranking/API; event frontend; discovery Settings;
browser QA harness. Request shared changes rather than editing others' files.

Old readers ignore new response fields; old draft writers omit optional metadata;
omitted PATCH fields preserve values. No backfilled profile inference. Review/apply
migration explicitly, never at startup. Downgrade refuses data-bearing new state
rather than silently deleting preferences or event metadata. No automatic drop.

## Acceptance

Prove lexicographic club priority, distinct normalized interests, exact area,
whole-window Manila fit/week wrap, missing-preference fallback, stable pagination
beyond first 50, chronology unchanged, search composition, draft privacy and user
isolation. Test validation/clear/persistence, optional metadata draft/publish,
conditional-save conflicts, migration preservation/guarded rollback and schema drift.
Run frontend contracts, localization, lint/build and actual local Edge desktop/
mobile journeys with saved preference changes, reasons and chronology. Screenshot
English/Filipino XL cases; retain participant/native-device test limitations.
Restore local frontend3000/API8001/worker after isolated tests on API8002.
