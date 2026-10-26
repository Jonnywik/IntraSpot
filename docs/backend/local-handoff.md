# IntraSpot local developer handoff

Checkpoint: Sprint 27 deployment preparation, 2026-10-26. This is a local developer handoff, not a
real-user launch. Current evidence and remaining gates belong in the
[Sprint 27 acceptance record](../validation/sprint-27-acceptance-2026-10-26.md).
Requirements remain in the canonical Obsidian AI Index and linked topic notes;
workspace copies and generated Graphify output are navigation, not authority.

## Profiles and ownership

| Profile | Frontend | API | Application SQL | Identity |
|---|---|---|---|---|
| Fictional local demonstration | `http://127.0.0.1:3000` | `http://127.0.0.1:8001` | `intraspot_mvp` | Fixed signed fictional accounts |
| Separate real development | `http://127.0.0.1:3001` | `http://127.0.0.1:8011` | `intraspot_real_dev` | Configured Supabase Google Auth |

Both databases use the dedicated loopback PostgreSQL 17 container on port 5433.
Supabase supplies Auth only; application SQL and normalized media remain local.
Media roots are partitioned by auth profile/environment. Never copy fictional
accounts into real development or use Penpot's database. Never expose the demo
catalog, database, API or static server beyond loopback.

## Start the existing configured checkout

Keep backend, deadline runner and frontend in separate terminals. Use the existing
environment files and virtual environment; no database reset, volume deletion,
broad seed or credential regeneration is needed for an existing checkout.

From `Code/Backend`, start its existing container:

```powershell
rtk proxy docker compose --env-file .env.local up -d --wait
rtk proxy .venv/Scripts/python.exe -m alembic current
```

The reviewed schema head is `mvp_0019`. If it is behind, review the pending
migration, then apply it explicitly with `rtk proxy .venv/Scripts/python.exe -m
alembic upgrade head`. Startup never performs migrations. Preserve a database
backup before a schema change; do not downgrade nonempty safety/attendance history.

For the fictional API, from `Code/Backend`:

```powershell
rtk proxy .venv/Scripts/python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log --log-level warning
```

For its explicit deadline runner, from the same folder in another terminal:

```powershell
rtk proxy .venv/Scripts/python.exe -m app.deadlines --interval 30
```

Use `--once` instead of `--interval 30` for a single catch-up pass. The runner
processes registration review/reconfirmation, content-report/chat retention,
invitations, announcement reports, event-report evidence expiry and suspension
expiry audit/notices. Access policy uses exact clock boundaries even between
passes; physical cleanup and notices may be late while the runner is stopped.
Restarting it catches up stored deadlines without resetting them.

From `Code/Frontend`, use the reviewed lockfile and start the fictional frontend:

```powershell
rtk proxy npm.cmd ci --ignore-scripts
rtk proxy npm.cmd run build
rtk proxy npm.cmd start
```

Open `http://127.0.0.1:3000/`. If the browser retained a connection-error page,
refresh after both servers are running. Check `/health` and `/ready` on port 8001.
Guest discovery needs no account. Use the clearly labeled fictional selector for
attendee/organizer/admin journeys. Renew expired fictional tokens only with
`rtk proxy .venv/Scripts/python.exe -m app.local_identities`; this fixed local
catalog operation preserves existing identities and writes ignored local files.
Never put signed tokens or private keys in frontend public assets or Git.

For real development, select the existing `INTRASPOT_CONFIG=real` backend profile
in that terminal's environment before running Uvicorn on **8011**, and select it
for that profile's deadline runner too. Do not apply it to the fictional test
commands. Use `npm.cmd run build:real` and `npm.cmd run start:real` from
`Code/Frontend`; both enforce the existing separate public configuration. Keep
provider secrets entered by the user directly in provider settings. Personal
Google sign-in was historically checked; current live PLM sign-in remains a
separate gate. New personal accounts start private/incomplete with no privileges.

## Verification and failure recovery

From `Code/Backend`, run database suites **serially**:

```powershell
rtk proxy .venv/Scripts/python.exe -m pytest tests -q
rtk proxy .venv/Scripts/python.exe -m pytest auth_tests -q
rtk proxy .venv/Scripts/python.exe -m alembic check
```

The default suite targets only `intraspot_mvp_test`; the synthetic-auth suite
targets only `intraspot_real_dev_test`. Importlib test mode prevents duplicate
module-name collisions. Browser opt-in tests stay skipped until a permitted
browser and the specified scratch build are available; a skip is not a pass.

From `Code/Frontend`, run tests, lint, TypeScript, audit and both exports. API types
come from the reviewed OpenAPI file; regenerate only when the API contract changes.
The current security patch pins Next/eslint-config-next to 16.4.1; the lockfile
updates the compatible Zod development dependency. Never suppress an advisory to
make a build pass, or use `npm audit fix --force` as an unreviewed upgrade plan.

### Rendered browser gates

The ten opt-in Sprint 5–14 gates and the Sprint 24 accessibility matrix use the
same named scratch PostgreSQL database and must run serially. They temporarily
own loopback API **8002** and frontend **3000**. Stop only your own normal
port-3000 static server first; the separate real app on 3001/8011 stays available.
Do not reuse a build pointing at development API 8001 for tests that create data.

Build the fictional test export from `Code/Frontend` in its existing configured
fictional terminal:

```powershell
$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8002'
rtk proxy npm.cmd run build
```

From `Code/Backend`, run the new matrix:

```powershell
$env:RUN_SPRINT24_BROWSER = '1'
rtk proxy .venv/Scripts/python.exe -m pytest tests/shared/test_sprint24_browser.py -q
```

Historical gates use `RUN_SPRINT5_BROWSER` through `RUN_SPRINT14_BROWSER` and
their corresponding `tests/shared/test_sprint*_browser.py` or
`test_sprint*_quality.py` files. Use the explicit paths shown in each file;
PowerShell does not expand a wildcard argument for pytest. The existing bundled
Playwright package and installed Microsoft Edge are required. A restricted-process
browser-launch failure is unavailable infrastructure, not a passing UI test.
Preserve raw run artifacts separately; do not overwrite historical evidence in
a checkpoint or discard unrelated local changes.

After the last gate, restore the normal frontend before leaving the app running:

```powershell
$env:NEXT_PUBLIC_API_URL = 'http://127.0.0.1:8001'
rtk proxy npm.cmd run build
rtk proxy npm.cmd start
```

Real sign-in now labels API-verified sessions and server-derived PLM eligibility
separately. A verified non-PLM Google account can browse while PLM-only actions
remain denied. The user deferred further positive PLM verification during Sprint
24; leave that gate open and keep credentials under their control.

If a process stops, inspect its own terminal, preserve the existing database
container/volume, and restart only that process. Do not use Docker factory reset.
Expected auth/validation/forbidden responses are not reasons to disable checks.
On an uncertain mutation retry the original request/key; on a version conflict
refresh and make a new explicit decision. A browser connection failure should
first be checked against the frontend and API ports, not worked around by
weakening firewall, network isolation or browser policy.

## Settled behavior to preserve

- Eligibility derives from verified `plm.edu.ph` or its true subdomains; platform
  privileges live server-side. Private profiles and account-scoped planning remain
  private. Registration needs a complete profile and a durable request key.
- Capacity and waitlist order are decided atomically in PostgreSQL by durable
  admission order. Approval/reconfirmation reserve seats; participant withdrawal
  and FIFO promotion retain their existing rules.
- Owners/admins draft while accreditation is pending, publish only after approval,
  and manage supported material changes with reconfirmation. Moderators have
  scoped reviews/attendance/safety authority, not owner/admin authoring privileges.
- Hide/suspension blocks new joins; existing reviews, deadlines, withdrawals,
  FIFO promotions and confirmed chat continue (2A). Independent hide channels
  restore separately. Cancellation/removal is terminal, ends active participation,
  and preserves audit/attendance history while denying new attendance writes.
- Mobile attendee navigation stays Discover, My Events, Chat, Settings. Management
  remains desktop-only. Text, contrast, theme, reduced motion and language settings
  remain independent. No new product features are implied by this handoff.

## Gates before real users

Keep browser interaction proof separate from HTTP/helper checks. Participant and
physical-device/full accessibility testing, live PLM-account verification,
retention/deletion and local-media reconciliation/quotas, operational/security
review and release approval remain separate. The accepted pilot decision does
not rehearse backup restoration before an actual incident; therefore restoration
readiness is **unverified**, not a passing gate. Preserve SQL and its matching
media partition together in private backups. Hosting, production scheduling,
cloud app-data migration and deployment require their own authorized work.
