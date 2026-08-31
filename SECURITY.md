# Security policy

Please do not open a public issue for a vulnerability that could expose visitor
identifiers, alter votes, access the database, or make the worker fetch an
attacker-controlled URL. Use GitHub's private vulnerability reporting for this
repository instead.

RomanPics intentionally has a narrow trust boundary:

- browser clients may search public metadata and mutate only their own votes;
- API clients cannot submit arbitrary upstream or preview URLs;
- the worker accepts jobs from the private database queue, validates HTTPS hosts
  and redirects, rejects private/link-local addresses, and enforces byte limits;
- upstream captions are rendered as text unless explicitly sanitized; and
- remote originals remain at their authoritative archives.

Security fixes target the current `main` branch. Reports should include the
affected endpoint or job, reproduction steps, impact, and a safe proof of
concept when possible. Do not include live credentials or visitor data.
