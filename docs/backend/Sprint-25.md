# Sprint 25 — hosted configuration and reproducible verification

Part of the user-authorized deployment preparation on 2026-10-26. This
checkpoint provides guarded evaluation configuration, not permission to deploy.

- Hosted backend reads process environment only; Supabase auth is required,
  fixture authentication forbidden, exact HTTPS origins and project-bound session
  pooler/TLS CA checks enforced for both runtime and migration credentials.
- Runtime pool is 3+2; local 15+5 pools and both local identity profiles remain
  unchanged. Alembic requires separate explicit hosted migration credentials.
- Explicit application hardening denies runtime administrative attributes,
  inherited roles and schema/table ownership; unknown public objects require
  review. Existing/future browser table grants are removed. Provider Data API
  disablement is a separate, unperformed cloud gate.
- Hosted frontend validates API/OAuth origins at build and runtime, refuses
  auto-loaded dotenv files, preserves local behavior, exports `out-hosted` and
  scans credential-shaped artifacts. Hosted copy is translated.
- Root Dockerfile uses the frozen Python lock, non-root UID 10001, one worker
  and a restricted build context. GitHub verification is manual-deployment-free.

See [evaluation runbook](hosted-evaluation.md), [approved sequence](Deployment-preparation.md)
and the Sprint 25 acceptance record for exact execution results and open gates.
