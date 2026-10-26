# Sprint 27: bounded runtime work and shared abuse controls

Hosted evaluation requires maintenance and rate limiting enabled, a separate
limiter key of at least 32 characters, and the explicit Koyeb edge policy.
Local/test profiles remain off by default and never trust forwarded addresses.
The container requires Koyeb service/instance identifiers, disables Uvicorn
forwarded-address rewriting and raw access logs, and runs one API worker.

Koyeb appends the connecting address to the right of X-Forwarded-For. The limiter
combines duplicate headers before selecting that address. This policy is valid
only when all ingress comes through Koyeb's managed edge; verification of the
actual deployed ingress remains an external gate. Do not reuse this trust policy
on a directly reachable server or behind another CDN without a new review.
[Provider contract](https://www.koyeb.com/docs/reference/edge-network),
[runtime identifiers](https://www.koyeb.com/docs/build-and-deploy/environment-variables).

Use `RATE_LIMIT_ENABLED=true`, `RATE_LIMIT_SECRET=<server-only random key>`,
`MAINTENANCE_ENABLED=true`, `TRUSTED_PROXY=koyeb` in hosted evaluation. No keys
belong in frontend settings. Keep the key stable across restarts and instances;
rotating it resets bucket identities. Health/readiness and CORS preflight are
excluded. Account limits supplement the shared IP limit; protected requests fail
closed with 503 if the shared limiter is unavailable. 429 includes Retry-After.

Only platform administrators can read `/api/v1/platform/operations`. Public
health/readiness reveal status only. Diagnostics contain generated correlation
IDs, matched route templates, status codes and sanitized exception categories.
They do not log request bodies, credentials or SQL exception messages.

No persistent volume is required for the public database CA: set
`SUPABASE_DATABASE_CA_PEM` to the provider's **public CA certificate**, and use
`sslrootcert=/tmp/intraspot-supabase-ca.pem` in both reviewed database URLs. The
entrypoint validates CA certificates and writes an ephemeral owner-only file.
Private keys are rejected. Existing CA-file configuration is also supported.
Database migrations remain explicit operator actions, never startup behavior.

The service performs a startup maintenance pass and continues only while awake.
Sleeping evaluation instances make no availability promise. Foreground deadline
catch-up remains in place. No artificial keepalive is added. Storage reconciliation
is a separate operator operation; it is not placed in the API maintenance loop.

Acceptance evidence is recorded separately after the serial PostgreSQL tests.
