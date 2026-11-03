# Sprint 30: integrated evaluation candidate

The candidate preserves the approved product behavior and schema mvp_0020.
Standalone rate-limit transactions queue before database checkout; at most 32
IP checks may be active or waiting for dispatch per process. Excess work fails
closed with 503. Health/readiness and preflight bypass limiter dispatch. Request
cancellation does not release dispatch capacity while its worker is still queued.

The regression suite covers 25 shared-IP chat sessions using the actual 3+2 pool,
ten registrations for three seats, stable retries, durable FIFO promotion and
worker interruption/restart. The additive migration rehearsal preserves existing
rows and the earlier registration contract. No populated history is downgraded.

The opt-in artifact rehearsal builds an earlier S28 source artifact and the
candidate, then starts S28, promotes the candidate and returns to S28. Both
artifacts retain reviewed mvp_0020 metadata. An arbitrary pre-migration artifact
is not a supported rollback. See the release ledger for measured results and
source/artifact hashes, and [Release runbook](Release-runbook.md) for promotion,
backup, recovery and rollback steps.

Local evidence is not hosted promotion or permission for public exposure. Actual
participants, physical Android/iOS, NVDA/VoiceOver, positive PLM verification,
provider configuration, off-provider scheduling/key custody and explicit release
approval remain required. Positive PLM testing stays deferred. No paid upgrade
or real-user deployment is authorized by this checkpoint.
