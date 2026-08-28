# Deploying Undiary

Nothing deploys yet. This file exists so the shape of the answer has
somewhere to live.

Planned: Cloud Run for the app, managed Postgres (Cloud SQL or Neon,
undecided), GCS for audio, Secret Manager for keys. Google OAuth
credentials and the allowlist arrive as environment variables; none of
them live in this repository.

When the first deploy happens, this file gets the one command, the
gotchas, and the DNS records for undiary.com, in that order.
