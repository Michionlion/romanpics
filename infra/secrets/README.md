# Runtime secrets

Compose reads secrets from files outside the checkout. Each PostgreSQL role has
its own password so an API or worker compromise does not expose the migration
owner or cluster bootstrap superuser. Passwords must be URL-safe because the
containers construct database URLs at startup. A 64-character hexadecimal value
satisfies that requirement.

Create the files without printing their values:

```bash
sudo install -d -m 700 -o root -g root /etc/romanpics/secrets
for secret_name in \
  postgres_bootstrap_password \
  postgres_migration_password \
  postgres_api_password \
  postgres_worker_password \
  visitor_signing_secret
do
  sudo install -m 600 -o root -g root /dev/null \
    "/etc/romanpics/secrets/$secret_name"
  openssl rand -hex 32 | \
    sudo tee "/etc/romanpics/secrets/$secret_name" >/dev/null
done
```

Do not add these files to Git, copy them into an image, or place their values in
`.env`. Back them up in the same encrypted system used for the PostgreSQL backup
key.

For an API, worker, or migration password rotation, replace its file atomically,
rerun `db-bootstrap`, then recreate only the affected long-running service:

```bash
docker compose --env-file /etc/romanpics/romanpics.env run --rm db-bootstrap
docker compose --env-file /etc/romanpics/romanpics.env up -d --force-recreate api
docker compose --profile worker --env-file /etc/romanpics/romanpics.env \
  up -d --force-recreate worker
```

The bootstrap password is different: PostgreSQL reads
`POSTGRES_PASSWORD_FILE` only when initializing an empty data directory. Change
that role's password through an authenticated maintenance session and replace
the file as one operation. Test the new login before ending the session.

Rotating the visitor signing secret signs every browser in as a new anonymous
visitor; existing votes remain stored but browsers no longer have their previous
identity cookie.
