# AI Redis authentication

The AI backend uses its own `redis-dev` / `redis-prod` instances. They are distinct
from the server instances named `redis_dev` / `redis_prod`. This change preserves
existing data mounts and does not publish Redis host ports.

Generate a separate random hex password for each environment. Put it in that
GitHub `REDIS_PASSWORD_DEV` / `REDIS_PASSWORD_PROD` secret and the matching
`.env.dev` / `.env.prod` as `REDIS_PASSWORD` for local operation. CD selects the
production secret only on `main`, otherwise the development secret; a missing
production secret cannot fall back to the development value. The sample value
is deliberately empty. Keep
`REDIS_URL` as the host/database URL without an embedded password; the application
loads the password separately from `REDIS_PASSWORD`. Do not configure conflicting
passwords in both places: redis-py gives URL credentials precedence.

Use `make up-dev` / `make up-prod`, or supply `docker compose --env-file .env.dev`
(or `.env.prod`) explicitly. Compose rejects a missing or empty password. Redis
receives only this credential, requires it on startup, and its healthcheck must
receive PONG using the same password. Unauthenticated or incorrect credentials
must fail; ordinary application credentials are unrelated.

Prepare the matching environment file before the first cutover. Compose resolves
required variables for all operations, including `make down-dev`, `make down-prod`,
status and logs; an old environment file without `REDIS_PASSWORD` cannot run those
commands until it is configured. This validation does not send an AUTH request to
the existing Redis instance or change its current password.

CD transports this secret without inserting its raw value into the remote shell.
It rejects missing/whitespace-only Redis passwords and multiline secrets, updates
the matching environment file, and validates Compose configuration before stopping
existing services. Use random hex values; arbitrary dotenv character formats are
not part of the deployment contract. Connection diagnostics omit URLs and log only
exception classes; do not put credentials in troubleshooting commands or tickets.

Before rollout, inventory actual consumers and configure both Redis and its AI
backend together. After dev deployment, verify unauthenticated and wrong-password
PING are denied, authorized PING and the healthcheck pass, and the app's JSON cache
roundtrip works. Delete only the smoke key created by that test. A source diff or
local container test is not proof that production has been secured.

Rotate the password in GitHub and coordinate a restart of Redis and the AI backend.
Do not restore anonymous Redis as a workaround. For a failed initial cutover,
preserve authentication and repair the client/configuration; later rollback must
use a known authenticated release and matching credential. This task does not
rotate other Redis instances, erase cache volumes, or change external consumers.
