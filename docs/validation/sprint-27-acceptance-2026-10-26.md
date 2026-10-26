# Sprint 27 acceptance — 2026-10-26

Scope: bounded awake maintenance, shared PostgreSQL limiter, private operations,
public status minimization, and client retry metadata. No hosted service was
deployed and no real PLM account was exercised.

Executed locally against isolated PostgreSQL 17:

- Hosted configuration: 39 passed. The first invocation could not create its
  system temporary directory; rerun with an in-workspace test directory passed.
- Shared operations/access and real HTTP capacity/restart: 22 passed.
- Migration preservation/rollback/readiness: 53 passed, 198 unrelated deselected.
- Final maintenance/limiter/operations/config/pool suite: 60 passed in 31.74 s.
  Includes two-process limiter contention/restart, duplicate proxy headers,
  bounded expiry, rollback/backoff, advisory-lock contention and FIFO batch size.
- Client recovery: six passed; explicit retry retains request contents/key and
  mutations are never retried implicitly. Lint and standalone types passed.
- Existing frontend regression: 156 passed. Independent review caught a poison
  target cursor-starvation case and nested account-limit connection contention.
  Budget exhaustion now advances the rolled-back target and records a partial
  failure using the separate finalization reserve; six maintenance checks passed.
  Account limiting reuses the read-only authentication session and commits before
  domain work, preserving the two spare connections without committing mutations.
- Final post-review combined suite: 26 passed in 83.39 s, including the real
  HTTP registration/restart journey, 12 limiter cases, six maintenance cases
  and seven operations/configuration cases. The independent assessor cleared the
  session reuse correction; the budget-starvation reproduction also passed.
- Container `intraspot-s27-evaluation` built with one worker, no raw access logs,
  no implicit proxy rewriting, and ephemeral public-CA handling.
- Reviewed OpenAPI and frontend types regenerated. Migration `mvp_0019` applied
  explicitly to both development schemas; no automatic startup migration added.
- No schema drift remains. Original 41-table projections match both baselines:
  76 fictional-development rows and two real-development rows preserved.

S26 remote CI exposed 27 stale migration assertions and three outdated media
mocks. This checkpoint uses the actual reviewed head and current read signature;
the affected migration/visibility suites passed. Remote CI for this checkpoint
is reported independently after push, not inferred from these local results.

Maintenance has a 100-target/20-second budget, with an 18-second work window,
short SQL/lock/connection waits and remaining transaction timeouts. It is a
bounded cooperative runner, not a real-time scheduling guarantee. Retry timers
reset on process restart; durable FIFO, cursor and outcome data do not. Sleeping
evaluation instances perform no work until awakened, with foreground catch-up
retained. Full two-process promotion/failure/load rehearsal remains Sprint 30.

Actual Koyeb ingress, verified hosted TLS/pooler/roles and Storage configuration
remain external gates. Human, physical-device, assistive-technology and positive
PLM checks remain pending/deferred. No participant result is claimed.
