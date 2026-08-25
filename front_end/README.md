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

The API reads `../back_end/product_importer/products.db` and its adjacent `media`
directory by default. Override these locations with `STRAIIT_DATABASE` and
`STRAIIT_MEDIA_ROOT` when needed. The SQLite connection is opened in read-only and
query-only modes.

Buyer accounts, sessions, demand requests, history, quotes, email delivery,
password resets, and reservations are stored separately
in `api/portal.db`. This prevents transactional portal data from being overwritten by
supplier catalogue imports. Override its path with `STRAIIT_PORTAL_DATABASE`.

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

Reservation creation uses a SQLite immediate transaction and rejects requests exceeding
imported quantity minus active allocations. The catalogue API reports net available
quantity while keeping the importer database read-only. Operators can confirm, release,
or allow holds to expire from `/admin`. Recovery commands include:

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
