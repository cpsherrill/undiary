# Deploying Undiary

Cloud Run serves Django; Firebase Hosting fronts it at undiary.com and
holds the certificate. Owner account: colin@crowable.com. GCP project:
`undiary`, region us-east4.

## The pieces

- Cloud Run service `undiary`, built from the repo's Dockerfile by
  `gcloud run deploy --source .`. Plain configuration rides in env
  vars; Secret Manager holds SECRET_KEY, GOOGLE_CLIENT_SECRET, and
  DATABASE_URL, mounted by the dedicated service account
  `undiary-run`.
- Cloud SQL Postgres 16, instance `undiary:us-east4:undiary`
  (db-f1-micro, daily backups at 08:00 UTC), reached over the unix
  socket from Cloud Run.
- Cloud Run job `undiary-migrate` runs migrations using the same
  image as the service.
- Firebase Hosting site `undiary` rewrites everything to the service
  (see firebase.json).

## Deploy (the two commands)

```sh
gcloud run deploy undiary --project=undiary --source . --region=us-east4
firebase deploy --only hosting --project undiary
```

Hosting only needs redeploying when firebase.json changes.

## Migrations

Point the job at the image the service is running, then run it:

```sh
gcloud run jobs update undiary-migrate --project=undiary --region=us-east4 \
  --image=$(gcloud run services describe undiary --project=undiary \
  --region=us-east4 --format="value(spec.template.spec.containers[0].image)")
gcloud run jobs execute undiary-migrate --project=undiary --region=us-east4 --wait
```

## Custom domain (still to do)

DNS lives on Route 53. Firebase console, Hosting, Add custom domain,
`undiary.com`; records match the rest of the fleet:

- `A` `@` -> `199.36.158.100`
- `TXT` `@` -> `hosting-site=undiary`

After the domain resolves, add
`https://undiary.com/accounts/google/login/callback/` to the OAuth
client (Google Auth Platform, Clients).

## Enrichment operations

The Anthropic key lives in Secret Manager as `anthropic-api-key`,
mounted on the service and both jobs. The sweep:

- Cloud Run job `undiary-enrich` runs `manage.py enrich_pending`
  (add `--args` overrides for `--all` when the watchlist changes).
- Cloud Scheduler `undiary-enrich-sweep` fires it every 15 minutes as
  the backstop; the inline pass after each save does the normal work.
- After a code deploy, point both jobs at the new image (same command
  as the migrate job's update, swapping the job name).

## Costs

Cloud SQL is the only real line item (db-f1-micro, roughly ten dollars
a month). Cloud Run scales to zero, and everything else rounds to
pennies.

## Status

First deploy shipped 2026-08-28; live at https://undiary.web.app with
sign-in working. Custom domain pending (records above). Gotchas for
next time, both from Firebase Hosting's proxy: it hands Cloud Run the
request with the backend's own hostname in Host and the real one in
X-Forwarded-Host, so production sets USE_X_FORWARDED_HOST (without it
every page is a 400); and its CDN strips every request cookie except
one named `__session`, so the Django session cookie is renamed to
that and the CSRF token lives in the session (without this, sign-in
dies at the OAuth callback and every form post 403s).
