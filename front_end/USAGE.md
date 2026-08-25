# Straiit Stock Portal usage guide

This guide explains how to run and use the stock portal as a visitor, buyer, or
trading-desk operator.

## Roles and access

| Role | Access |
| --- | --- |
| Visitor | Browse and filter the catalogue, view products and contact support. |
| Buyer | All visitor features, plus submit and track demand requests. |
| Operator | Review buyer applications, manage requests and quotes, reserve stock, confirm offline payment, and audit email delivery. |

Buyer and operator accounts use the same sign-in dialog but have different access.
Open `/admin` and select **Sign in as operator** to enter the operator area.

## Run the application locally

From `front_end`, install the frontend packages once:

```powershell
npm install
```

Start the API in one terminal:

```powershell
npm run api
```

Start the frontend in another terminal:

```powershell
npm run dev
```

Open `http://localhost:5173`. Vite sends `/api` and `/media` requests to the
Python API at `http://127.0.0.1:8787`.

By default, the API uses:

- `../back_end/product_importer/products.db` for the read-only product catalogue.
- `../back_end/product_importer/media/` for product images.
- `api/portal.db` for accounts, sessions, requests, quotes, reservations, password resets, and queued email.

The API creates and upgrades `api/portal.db` automatically. It does not modify
the catalogue database.

## Browse the catalogue

1. Select **Stock list** in the main navigation.
2. Search by product name, brand, model, SKU, or barcode.
3. Optionally filter by brand, category, status, or explicit stock availability.
4. Select a product to view its quantity, pricing, variants, specifications, and supplier MOQ tiers.
5. Use **Ask about this product** to compose a general email enquiry, or use the buyer request form further down the product page.

Displayed availability is the imported catalogue quantity minus any active stock
holds or confirmed reservations. A fully allocated product is marked **Fully
reserved**.

## Apply for buyer access

1. Select **Request access**.
2. Enter the registered company name, country, work email, and a password of at least 12 characters.
3. Add a VAT or import-licence number when applicable.
4. Submit the application.

The application remains pending until an operator approves it. The applicant
cannot sign in while approval is pending. Approval creates the buyer account
using the password supplied in the application.

## Sign in as a buyer

1. Select **Sign in**.
2. Confirm that the dialog says **Buyer area**.
3. Enter the approved work email and password.
4. Open **Demand requests** to view requests belonging to the buyer's organisation.

All authorised buyers in the same organisation can see that organisation's
requests.

## Request listed stock

1. Sign in with an approved buyer account.
2. Open the required product from **Stock list**.
3. Find **Ask about this stock**.
4. Enter the required quantity and destination.
5. Optionally enter a target unit price and requirements such as packaging, size mix, labelling, or delivery timing.
6. Select **Submit demand request**.

The portal creates a reference such as `DR-000012` and opens **My requests**.
Submitting a request does not reserve the product. The trading desk must review
the request, issue a quote, and place the stock on hold.

## Request stock that is not listed

1. Open **Demand requests**.
2. Select **Request unlisted stock**.
3. Describe the brand or brand tier, category, quantity, target price, destination, and any detailed requirements.
4. Select **Submit demand request**.

This creates standing demand that the trading desk can use when sourcing stock or
reviewing future catalogue imports. Because it is not attached to a catalogue
product, it cannot create an automatic stock hold.

## Understand request and reservation status

| Request status | Meaning |
| --- | --- |
| `new` | Submitted and awaiting trading-desk review. |
| `reviewing` | The request is being checked. |
| `sourcing` | Availability or alternative supply is being investigated. |
| `quoted` | A commercial quote has been issued. |
| `accepted` | Listed stock has been placed on hold pending or following offline payment. |
| `closed` | The request has finished or its reservation was released. |
| `rejected` | The trading desk declined the request. |

| Reservation status | Meaning |
| --- | --- |
| `held` | Stock is temporarily allocated until the quote's payment deadline. |
| `confirmed` | Offline payment was confirmed and the allocation is firm. |
| `released` | The allocation was cancelled and returned to available stock. |
| `expired` | Payment was not confirmed before the deadline, so the hold was removed. |

Payments take place outside the portal, for example by bank transfer or invoice.
There is no card checkout and buyers cannot place or confirm their own holds.

## Reset a password

1. Open **Sign in** and select **Forgot your password?**
2. Enter the account email and select **Send reset link**.
3. Open the one-time link in the email.
4. Choose a new password of at least 12 characters.

Reset links expire after 30 minutes and can be used only once. Completing a reset
signs out all existing sessions. For privacy, the request screen gives the same
response whether or not the email belongs to an active account.

If SMTP is not configured, the reset email remains queued and appears in the
operator delivery audit, but the user cannot complete recovery until the message
is delivered.

## Create an operator account

From `front_end`, run:

```powershell
python api/manage.py create-operator operations@example.com --name "Trading desk"
```

The command prompts for a password. Password entry is deliberately invisible:
the terminal does not show characters, dots, or cursor movement while typing.
Type a password of at least 12 characters and press Enter.

For automated setup, a password can be supplied with `--password`, but doing so
can expose it in shell history and process information.

## Use the trading desk

1. Open `/admin`.
2. Select **Sign in as operator**.
3. Confirm that the dialog says **Operator area**.
4. Enter an operator account email and password.

The trading desk shows pending applications, open demand, active reservations,
and queued email.

### Review buyer applications

- Select **Approve** to create an active buyer account.
- Select **Reject** to decline the application.

The applicant receives a queued notification for either outcome.

### Process a demand request

1. Find the request under **Demand requests**.
2. Update its status and optionally enter a buyer-facing note.
3. Enter the total quote amount, three-letter currency, payment deadline, and offline payment terms.
4. Select **Issue quote**.
5. For a quoted request attached to a catalogue product, select **Place stock on hold**.

A hold uses an immediate database transaction and is rejected if another active
allocation has consumed the requested quantity. Its expiry is taken from the
quote's payment deadline.

### Complete or release a reservation

- Select **Confirm payment** after offline payment has cleared. This makes the reservation firm.
- Select **Release** to cancel an active allocation and return the quantity to available stock.

Expired holds are removed automatically when reservation data is read. They can
also be expired explicitly with the management command shown below.

### Audit email

The **Recent email** table shows each recipient, subject, delivery status, attempt
count, and latest delivery error. Email remains queued until SMTP is configured
and the dispatcher successfully sends it.

## Operator command reference

Run these commands from `front_end`:

```powershell
# Applications
python api/manage.py list --status pending
python api/manage.py approve 12
python api/manage.py reject 12 --note "Unable to verify registration"

# Demand requests
python api/manage.py requests --status new
python api/manage.py request-status DR-000012 reviewing --note "Checking availability"
python api/manage.py quote DR-000012 12500 EUR --valid-until 2026-09-30 --terms "Bank transfer"

# Reservations and email
python api/manage.py expire-reservations
python api/manage.py release-reservation 42 --note "Order cancelled"
python api/manage.py send-emails
```

Use `python api/manage.py <command> --help` to see the arguments for an individual
command. Set `STRAIIT_PORTAL_DATABASE` before running a command if the portal
database is stored somewhere other than `api/portal.db`.

## Production settings

Serve the frontend and API from the same HTTPS origin where possible. At minimum,
set:

```text
STRAIIT_PUBLIC_URL=https://stock.example.com
STRAIIT_ALLOWED_ORIGINS=https://stock.example.com
STRAIIT_COOKIE_SECURE=1
```

Store the catalogue, portal database, media, and SMTP credentials outside the Git
checkout. Back up the writable portal database regularly. Never publish either
database or an environment file as a downloadable static asset.

## Troubleshooting

- A `401` response from `/api/auth/me` is normal before a user signs in.
- If `/admin` says **Buyer area**, close the dialog and reopen it with **Sign in as operator** from `/admin`.
- If operator creation appears to hang, type the password and press Enter; the secure prompt does not echo input.
- If email stays queued, check the SMTP environment variables and the **Recent email** delivery error.
- If products or images are missing, verify `STRAIIT_DATABASE` and `STRAIIT_MEDIA_ROOT` point to the imported catalogue and media directory.
- Only one API process can listen on port 8787. Stop the existing process before starting another.
