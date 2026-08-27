# Straiit Stock Portal

React frontend and read-only catalogue API for the existing Straiit product-import database.

For complete visitor, buyer, and operator instructions, see the
[usage guide](USAGE.md).

## Development

Run the API in one terminal:

```powershell
npm run api
```

Run the frontend in another terminal:

```powershell
npm run dev
```

Vite proxies `/api` and `/media` to `http://127.0.0.1:8787`.

Without a database URL, the API uses the local SQLite files. It reads
`../back_end/product_importer/products.db` and its adjacent `media` directory by
default; override these locations with `STRAIIT_DATABASE` and
`STRAIIT_MEDIA_ROOT` when needed. The catalogue SQLite connection is opened in
read-only and query-only modes.

Buyer accounts, sessions, demand requests, history, quotes, email delivery,
password resets, and reservations are stored separately
in `api/portal.db`. This prevents transactional portal data from being overwritten by
supplier catalogue imports. Override its path with `STRAIIT_PORTAL_DATABASE`.

### Run against Neon

The local database toggle is [api/runtime.local.json](api/runtime.local.json):

```json
{
  "use_neon": true,
  "neon_database_url": "postgresql://user:password@host/database?sslmode=require"
}
```

Set it to `true` for Neon or `false` for the two local SQLite databases, then restart
the API. Paste your Neon connection string into `neon_database_url`. This local file
is ignored by Git so the credential cannot be committed accidentally. If it is missing,
copy `api/runtime.example.json` to `api/runtime.local.json`.

Environment variables remain supported when the local URL is blank or the local file is
absent. They are recommended for deployment. If only the direct migration variable is
currently set, you can save it once for your Windows user:

```powershell
[Environment]::SetEnvironmentVariable("DATABASE_URL", $env:NEON_DIRECT_DATABASE_URL, "User")
```

Open a new terminal after setting it. Thereafter, switching the JSON toggle is all
that is required before starting the API:

```powershell
npm run api
```

The API automatically switches both catalogue reads and portal writes to the
`catalogue` and `portal` schemas in that Neon database. `NEON_DATABASE_URL` and
`NEON_DIRECT_DATABASE_URL` are also accepted as local fallbacks. For a hosted
deployment, use Neon's pooled connection string as `DATABASE_URL`; keep the direct
connection string for migrations. A deployment can override the local toggle with
`STRAIIT_USE_NEON=true`.

Confirm which backend is active after starting the API:

```powershell
Invoke-RestMethod http://127.0.0.1:8787/api/health
```

The response includes `database: postgresql` when Neon is active. If no supported
database URL is present, the application deliberately continues to use SQLite.

### Remote product images

Catalogue image records retain their existing `media/...` paths. Set
`media_base_url` in the ignored `api/runtime.local.json` file to serve those paths
from an S3 bucket without changing either database:

```json
{
  "media_base_url": "https://straiit-stock-media.s3.eu-west-2.amazonaws.com/"
}
```

For deployment, use `STRAIIT_MEDIA_BASE_URL` when no local runtime file is present.
Leave the value empty to serve files from the local `STRAIIT_MEDIA_ROOT`. The health
endpoint reports `media: remote` or `media: local` so the active mode can be checked.

## Buyer account approval

Applications submitted through the portal remain pending until reviewed. List them:

```powershell
npm run accounts:list
```

Approve or reject an application by ID:

```powershell
python api/manage.py approve 12
python api/manage.py reject 12 --note "Unable to verify registration"
```

Approval creates the organisation and buyer user. The applicant can then sign in
with the password chosen during application.

## Operator console

Create the first operator account (the password prompt avoids shell history):

```powershell
python api/manage.py create-operator operations@example.com --name "Trading desk"
```

Sign in with that account and open `/admin`. The console supports account approval,
request status updates, quote issuance, reservation release, and email-delivery audit.
The equivalent CLI commands remain available for recovery and automation.

## Trading-desk request workflow

List incoming requests, move a request through its workflow, or issue a quote:

```powershell
python api/manage.py requests --status new
python api/manage.py request-status DR-000012 reviewing --note "Checking availability"
python api/manage.py quote DR-000012 12500 EUR --valid-until 2026-09-30 --terms "EXW Rotterdam"
```

Status and quote changes are persisted and appear on the buyer dashboard.

## Email and password recovery

Notifications are written to a durable outbox and delivered by the API's background
dispatcher. Configure an SMTP service before starting the API:

```powershell
$env:STRAIIT_SMTP_HOST = "smtp.example.com"
$env:STRAIIT_SMTP_PORT = "587"
$env:STRAIIT_SMTP_USERNAME = "smtp-user"
$env:STRAIIT_SMTP_PASSWORD = "smtp-password"
$env:STRAIIT_EMAIL_FROM = "Straiit Stock <sales@example.com>"
$env:STRAIIT_PUBLIC_URL = "https://stock.example.com"
```

STARTTLS is enabled by default. Use `STRAIIT_SMTP_SSL=1` for implicit TLS, or
`STRAIIT_SMTP_STARTTLS=0` only for a trusted local relay. Without SMTP configuration,
messages remain queued and visible in the operator console. Retry them with
`python api/manage.py send-emails`.

Password-reset requests return the same response whether or not an account exists,
are rate limited, expire after 30 minutes, are single use, and revoke all sessions.

## Offline payments and stock reservations

Buyers request listed or unlisted stock, but cannot reserve inventory directly. After
issuing a quote, an operator can place listed stock on hold in `/admin`. The hold uses
the quote's payment deadline and is confirmed by the operator after receiving offline
payment, such as a bank transfer or invoice settlement.

Reservation creation uses a database transaction and rejects requests exceeding
imported quantity minus active allocations. PostgreSQL uses a transaction-scoped
advisory lock per product so concurrent operators cannot oversell it. The catalogue API
reports net available quantity while keeping catalogue records read-only. Operators can
confirm, release, or allow holds to expire from `/admin`. Recovery commands include:

```powershell
python api/manage.py release-reservation 42 --note "Order cancelled"
python api/manage.py expire-reservations
```

For production, serve the app and API on the same HTTPS origin and set
`STRAIIT_COOKIE_SECURE=1`. If the frontend uses a separate origin, list it explicitly
in `STRAIIT_ALLOWED_ORIGINS`.

## Checks

```powershell
npm run lint
npm test
npm run build
npm run api:test
```

The original Claude design export remains in this directory as a visual reference.

## One-time Neon data migration

The migration command creates `catalogue` and `portal` schemas, creates their
PostgreSQL tables, copies both local SQLite databases while preserving IDs, resets
identity sequences, and verifies every table count in one transaction.

Install the PostgreSQL driver and validate the local sources first:

```powershell
python -m pip install -r api/requirements.txt
python api/migrate_to_neon.py --check-only
```

Copy the direct, non-pooled connection string from the Neon **Connect** dialog and
set it only in the current terminal:

```powershell
$env:NEON_DIRECT_DATABASE_URL = "postgresql://..."
python api/migrate_to_neon.py
```

The command refuses to write when its target tables already contain data. Use
`--replace` only when you deliberately want to drop and recreate the `catalogue`
and `portal` schemas. The connection string is never printed or stored by the
script.

This migrates the product-image database records, not the image files themselves;
the media directory still needs to be published to object storage. Set `DATABASE_URL`
as described above to switch the running application to Neon.
