# Hosted evaluation runbook

This profile prepares a controlled evaluation, not a public release. Use a new,
empty Supabase project and never import either local development dataset.
Provider configuration, actual TLS connectivity and live OAuth require separate
available access; local protocol tests are not proof those settings were applied.

## Render UAT alternative

On 2026-11-03 the user approved Render Free instead of Koyeb after the new
Koyeb account offered no free deployment. Render is an additional supported
boundary; the local and Koyeb profiles remain available. Select
`TRUSTED_PROXY=render` and the exact assigned HTTPS `*.onrender.com` API origin.
Startup validates Render's documented web-service identity and matching external
hostname/URL. Do not set provider identity variables yourself.

Use the existing root Dockerfile, one worker, no persistent disk, manual deploys,
and `/ready` as the HTTP health-check path. Retain Supabase for durable data and
private media; do not provision a Render database. Keep the compute plan Free,
do not add billing or upgrade automatically, and expect cold starts after idle.

For this boundary only, the limiter consumes one valid `CF-Connecting-IP` header
and ignores `X-Forwarded-For`. Missing or ambiguous connecting-IP headers fail
closed. Before marking the host verified, check that Render's public ingress
overwrites forged connecting-IP headers and that changing forwarded headers
does not create extra IP-limit buckets. Local unit tests alone cannot prove the
provider's live forwarding behavior.

Current provisioning evidence and outstanding actions are tracked in
[UAT provisioning](UAT-provisioning.md). A reserved hostname is not a deployed
or verified application.

## Environment and database roles

Runtime secrets are injected by the host, never placed in Git or a frontend
`NEXT_PUBLIC_` variable. Set `INTRASPOT_CONFIG=hosted`, `AUTH_PROVIDER=supabase`,
`FIXTURE_AUTH=false`, `PUBLIC_API_URL` and exact JSON `CORS_ORIGINS` HTTPS roots.
Supply the project's public Supabase URL/publishable key. `DATABASE_URL` uses
the session pooler on 5432, database `postgres`, `app_runtime.<project-ref>`,
`sslmode=verify-full`, and an absolute mounted CA path in `sslrootcert`.

The database operator must first create separate non-administrative login roles
`app_migrator` and `app_runtime` using privately entered/generated passwords.
Neither receives superuser, createdb, createrole, bypassrls or role memberships.
In this dedicated empty project, the migration role owns the application tables
and the `public` schema so it can manage application grants. Do not change the
`auth`, `storage`, extension or other provider-managed schemas/objects. Unexpected
public tables/views or non-extension functions require review before proceeding.

Disable the project's Data API in provider settings. Review and explicitly apply
Alembic with `MIGRATION_DATABASE_URL` using the migration role, same project and
verified endpoint. Then run `python -m app.hosted_security --runtime-role
app_runtime --migration-role app_migrator` in that migration environment. Remove
migration credentials from the API runtime. Reapply the permission check after
every migration. Confirm direct REST/GraphQL reads using both publishable and
authenticated clients cannot obtain application data. Local SQL grants alone do
not prove the provider Data API toggle was disabled.

## Builds and promotion

The root Dockerfile installs the frozen Python lock, excludes local credentials,
runs as UID 10001 and serves one Uvicorn worker. Runtime pooling is 3+2. Never
run migrations at API startup or raise worker count without a connection budget.

Build the frontend from a clean checkout with `npm ci` then `npm run build:hosted`.
Set `NEXT_PUBLIC_DEPLOYMENT=hosted`, `NEXT_PUBLIC_LOCAL_DEMO=false`,
`NEXT_PUBLIC_AUTH_MODE=supabase`, exact `NEXT_PUBLIC_API_URL` and
`NEXT_PUBLIC_FRONTEND_ORIGIN`, plus the public Supabase URL/publishable key. No
Next-loadable dotenv files may be present. Publishable keys are public; database,
Storage administrator, Google client and signing secrets never belong here.
The output is `out-hosted`; callback is the exact frontend origin plus
`/auth/callback`. Preview domains are not automatically trusted.

Before promotion: green required checks, reviewed additive migration, paired
backup, private remote media, runner/limiter verification, human release gates
and explicit approval. Keep the previous backend/frontend artifacts; roll back
application artifacts rather than downgrading populated history. Deployment is
manual; the verification workflow does not deploy or spend money.
