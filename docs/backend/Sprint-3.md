# Sprint 3 — Events and public discovery

Authorized 2026-10-13. Complete this sprint only. The main chat orchestrates five GPT-6 Luna/max workers; the tool does not expose a fast-mode setting.

## Frozen behavior

- Reuse the synchronous FastAPI/PostgreSQL modular monolith and reviewed `mvp_0001` schema. No startup migrations, database resets, cloud services, or Penpot changes.
- Eligible active organization owners/admins may save incomplete drafts and see private previews. Pending organizations may draft but cannot publish. Rejected organizations stay read-only. Only approved organizations may publish.
- Publishing requires nonblank title, description, venue name/address and one of `heritage`, `design`, `garden`, `music` artwork keys; aware future start, end after start, positive capacity. Only scheduled/instant events are supported. Summary is optional and defaults to an empty string; cost is informational.
- Public projection and HTTP routes remain as frozen in `Contracts.md`. Public responses never contain creator/registrant identities or private profile fields. Drafts are not publicly discoverable.
- Search matches literal event-title/organization-name substrings, not venues. Search, My Clubs and sorting compose. Upcoming is start ascending then ID ascending; Newest is publication descending then ID ascending. Active discovery includes ongoing but excludes ended events. Published historical details remain readable.
- My Clubs requires an eligible signed-in actor and active memberships; an eligible user with none receives an empty list. The existing actor grants expose whether the future frontend can show this filter.
- Published events cannot be patched or cancelled. Registration at/after start is denied; this sprint tests the boundary without accepting or expanding Sprint 4.
- Keep the existing durable registration catch-up seam intact. Attendance, remaining seats and interest are independent public values.
- Quality-review exception: the coordinator fixes the existing intake/publication seam to prevent unfinished private-draft attempts from becoming valid registrations after publication. New draft intake is rejected; legacy pending draft receipts become rejected atomically with publication. This is a Sprint 3 privacy fix, not acceptance or expansion of Sprint 4.

## Non-overlapping ownership

| Worker | Exclusive write scope |
|---|---|
| Draft/publish | `app/domains/events/schemas.py`, `service.py`, `tests/events/test_sprint3_drafts.py` |
| Discovery | `app/domains/events/routes.py`, `tests/events/test_sprint3_discovery.py` |
| Lifecycle | `tests/events/test_sprint3_lifecycle.py` |
| Local event fixtures | `app/local_events.py`, `tests/shared/test_local_events.py` |
| Quality assessor | `tests/quality/test_sprint3_quality.py`, `docs/validation/sprint3-quality-review.md`; production fixes only after the coordinator releases ownership |

All paths above are relative to `Code/Backend`, except the quality review document. The coordinator owns contracts, shared infrastructure, migrations, router assembly, dependencies, live acceptance scripts and handoff. Other existing source/test files are not worker-owned. No descendants or commits.

## Verification discipline and exit

All pytest runs use real PostgreSQL on loopback port 5433, with guarded resets only in `intraspot_mvp_test`. Never run pytest concurrently: per-test reset is shared. Workers prepare regressions and request a serial test slot; the coordinator runs the combined gate.

Exit requires prior sprint regressions plus draft/publish, permission/privacy, composed search/sort/My Clubs, counts and lifecycle tests; a persisted local HTTP demonstration and restart check; reviewed OpenAPI and an honest handoff. Frontend integration, participant testing, deployment and new registration workflows remain deferred.
