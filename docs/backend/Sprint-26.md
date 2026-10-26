# Sprint 26 — private durable media and storage accounting

Implements the approved media slice; no actual cloud bucket or provider secret
has been provisioned. Hosted configuration now requires a server-only Storage
secret and private Supabase media. Local development keeps its local adapter.

- Additive `mvp_0018` creates a durable ledger and accounts for legacy media
  without rewriting original metadata or moving bytes. Runtime quotas include
  retained objects and committed reservations: 50 MiB/org, 500 MiB globally.
- Independent reservation transactions serialize quota admission before writes;
  the ledger deliberately has no organization FK that could deadlock against
  the upload transaction's existing organization lock. Object names are immutable.
- Private Supabase requests use the `apikey` header, never treat the new secret
  as a bearer JWT, refuse redirects/public buckets and bound time/response size.
  Existing API attachment and privacy checks precede proxied reads.
- Reads reuse the authorized DB session; hosted request admission leaves two
  pool connections for durable reservations. Provider/metadata failures return
  sanitized 503 responses rather than exposing private data or pretending 404.
- Reconciliation defaults to a dry-run manifest. `--record-observations` records
  sightings only. Candidate age is 14 days with separated weekly observations,
  no live references and no active backup/report hold. Missing referenced objects
  stay protected; ambiguous writes stay charged. Sprint 28 supplies explicit,
  revalidated physical cleanup/release; this sprint never deletes objects.
- Existing layout is unchanged. Upload quota/outage feedback is translated and
  preserves the selected file and existing image after a failed mutation.

Run `python -m app.media_reconcile` for a dry run; add
`--record-observations` only to persist sightings. Store manifests privately.
Deploy only after creating the private bucket and entering the secret directly
into the backend host's secret storage. Set `MEDIA_PROVIDER=supabase`,
`MEDIA_BUCKET=intraspot-media` and `SUPABASE_STORAGE_SECRET`; never expose that
secret through frontend variables. Verify real provider behavior before cutover.
