from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


PORTAL_DATABASE = Path(__file__).resolve().parent / "portal.db"
PASSWORD_ITERATIONS = 600_000
SESSION_LIFETIME = timedelta(days=7)
REQUEST_TYPES = {"stock", "wanted"}
REQUEST_STATUSES = {"new", "reviewing", "sourcing", "quoted", "accepted", "closed", "rejected"}
RESERVATION_STATUSES = {"held", "confirmed", "released", "expired"}
RESET_LIFETIME = timedelta(minutes=30)


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    registration_number TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS account_applications (
    id INTEGER PRIMARY KEY,
    company_name TEXT NOT NULL,
    registration_number TEXT,
    country TEXT NOT NULL,
    email TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    review_note TEXT
);
CREATE INDEX IF NOT EXISTS idx_applications_email ON account_applications(email);
CREATE INDEX IF NOT EXISTS idx_applications_status ON account_applications(status);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'buyer' CHECK(role IN ('buyer','operator')),
    status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','suspended')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS demand_requests (
    id INTEGER PRIMARY KEY,
    reference TEXT UNIQUE,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    created_by INTEGER NOT NULL REFERENCES users(id),
    request_type TEXT NOT NULL CHECK(request_type IN ('stock','wanted')),
    product_id INTEGER,
    product_snapshot_json TEXT,
    brand TEXT,
    category TEXT,
    quantity REAL NOT NULL CHECK(quantity > 0),
    target_price REAL,
    currency TEXT,
    destination TEXT NOT NULL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','reviewing','sourcing','quoted','accepted','closed','rejected')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_requests_organization ON demand_requests(organization_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_requests_status ON demand_requests(status);

CREATE TABLE IF NOT EXISTS request_status_history (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES demand_requests(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    note TEXT,
    changed_by INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quotes (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES demand_requests(id) ON DELETE CASCADE,
    amount REAL NOT NULL,
    currency TEXT NOT NULL,
    valid_until TEXT,
    terms TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open','accepted','expired','withdrawn')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_password_resets_expiry ON password_reset_tokens(expires_at);

CREATE TABLE IF NOT EXISTS email_outbox (
    id INTEGER PRIMARY KEY,
    to_email TEXT NOT NULL,
    subject TEXT NOT NULL,
    text_body TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','sending','sent','failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL,
    sent_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_email_outbox_status ON email_outbox(status, created_at);

CREATE TABLE IF NOT EXISTS reservations (
    id INTEGER PRIMARY KEY,
    request_id INTEGER NOT NULL REFERENCES demand_requests(id) ON DELETE CASCADE,
    quote_id INTEGER NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL,
    organization_id INTEGER NOT NULL REFERENCES organizations(id),
    quantity REAL NOT NULL CHECK(quantity > 0),
    status TEXT NOT NULL DEFAULT 'held' CHECK(status IN ('held','confirmed','released','expired')),
    expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reservations_product ON reservations(product_id, status, expires_at);
CREATE INDEX IF NOT EXISTS idx_reservations_request ON reservations(request_id, created_at DESC);

"""


@dataclass(frozen=True)
class AuthUser:
    id: int
    organization_id: int
    email: str
    display_name: str | None
    company_name: str
    country: str
    registration_number: str | None
    role: str


class PortalError(ValueError):
    pass


class ConflictError(PortalError):
    pass


def now() -> datetime:
    return datetime.now(UTC)


def timestamp(value: datetime | None = None) -> str:
    return (value or now()).isoformat(timespec="seconds")


def normalize_email(value: Any) -> str:
    email = str(value or "").strip().casefold()
    if len(email) > 254 or "@" not in email or email.startswith("@") or email.endswith("@"):
        raise PortalError("Enter a valid work email.")
    local, domain = email.rsplit("@", 1)
    if not local or "." not in domain:
        raise PortalError("Enter a valid work email.")
    return email


def required_text(value: Any, label: str, maximum: int = 200) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        raise PortalError(f"{label} is required.")
    if len(text) > maximum:
        raise PortalError(f"{label} is too long.")
    return text


def optional_text(value: Any, maximum: int = 2_000) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > maximum:
        raise PortalError("A submitted field is too long.")
    return text


def validate_password(password: Any) -> str:
    value = str(password or "")
    if len(value) < 12:
        raise PortalError("Password must be at least 12 characters.")
    if len(value) > 128:
        raise PortalError("Password must be at most 128 characters.")
    return value


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations)
        )
        return hmac.compare_digest(candidate, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


def connect_portal(database: Path = PORTAL_DATABASE, *, use_wal: bool = True) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if use_wal:
        connection.execute("PRAGMA journal_mode = WAL").fetchone()
    return connection


def ensure_schema(database: Path = PORTAL_DATABASE) -> None:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = connect_portal(database, use_wal=False)
    try:
        connection.executescript(SCHEMA)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        if "role" not in columns:
            connection.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'buyer'")
        connection.commit()
    finally:
        connection.close()


def submit_application(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    company = required_text(payload.get("company"), "Company")
    country = required_text(payload.get("country"), "Country")
    registration = optional_text(payload.get("registration_number"), 120)
    email = normalize_email(payload.get("email"))
    password = validate_password(payload.get("password"))
    if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
        raise ConflictError("An account already exists for this email.")
    if connection.execute(
        "SELECT 1 FROM account_applications WHERE email = ? AND status = 'pending'", (email,)
    ).fetchone():
        raise ConflictError("An application is already pending for this email.")
    cursor = connection.execute(
        "INSERT INTO account_applications (company_name,registration_number,country,email,password_hash) VALUES (?,?,?,?,?)",
        (company, registration, country, email, hash_password(password)),
    )
    queue_email(
        connection,
        email,
        "We received your Straiit account application",
        f"Your application for {company} has been received and is awaiting review.",
    )
    queue_email(
        connection,
        os.environ.get("STRAIIT_OPERATOR_EMAIL", "sales@straiit.trade"),
        f"New buyer application: {company}",
        f"Application #{cursor.lastrowid} from {email} is ready for review in the operator console.",
    )
    connection.commit()
    return {"id": cursor.lastrowid, "status": "pending", "email": email}


def list_applications(connection: sqlite3.Connection, status: str = "pending") -> list[dict[str, Any]]:
    return [dict(row) for row in connection.execute(
        "SELECT id,company_name,registration_number,country,email,status,created_at,reviewed_at,review_note "
        "FROM account_applications WHERE status = ? ORDER BY created_at", (status,)
    )]


def approve_application(connection: sqlite3.Connection, application_id: int) -> dict[str, Any]:
    application = connection.execute(
        "SELECT * FROM account_applications WHERE id = ?", (application_id,)
    ).fetchone()
    if not application or application["status"] != "pending":
        raise PortalError("Pending application not found.")
    if connection.execute("SELECT 1 FROM users WHERE email = ?", (application["email"],)).fetchone():
        raise ConflictError("An account already exists for this email.")
    try:
        organization_id = connection.execute(
            "INSERT INTO organizations (name,country,registration_number) VALUES (?,?,?)",
            (application["company_name"], application["country"], application["registration_number"]),
        ).lastrowid
        user_id = connection.execute(
            "INSERT INTO users (organization_id,email,password_hash) VALUES (?,?,?)",
            (organization_id, application["email"], application["password_hash"]),
        ).lastrowid
        connection.execute(
            "UPDATE account_applications SET status='approved',reviewed_at=? WHERE id=?",
            (timestamp(), application_id),
        )
        queue_email(
            connection,
            application["email"],
            "Your Straiit buyer account is approved",
            "Your buyer account is now active. You can sign in and submit or track demand requests.",
        )
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    return {"application_id": application_id, "organization_id": organization_id, "user_id": user_id}


def reject_application(connection: sqlite3.Connection, application_id: int, note: str | None = None) -> None:
    application = connection.execute(
        "SELECT email FROM account_applications WHERE id=? AND status='pending'", (application_id,)
    ).fetchone()
    cursor = connection.execute(
        "UPDATE account_applications SET status='rejected',reviewed_at=?,review_note=? WHERE id=? AND status='pending'",
        (timestamp(), optional_text(note, 500), application_id),
    )
    if cursor.rowcount != 1:
        raise PortalError("Pending application not found.")
    queue_email(
        connection,
        application["email"],
        "Update on your Straiit account application",
        "We could not approve your application at this time." + (f"\n\n{note}" if note else ""),
    )
    connection.commit()


def authenticate(connection: sqlite3.Connection, email_value: Any, password_value: Any) -> AuthUser | None:
    try:
        email = normalize_email(email_value)
    except PortalError:
        return None
    password = str(password_value or "")
    row = connection.execute(
        "SELECT u.id,u.organization_id,u.email,u.password_hash,u.display_name,u.role,u.status,"
        "o.name company_name,o.country,o.registration_number,o.status organization_status "
        "FROM users u JOIN organizations o ON o.id=u.organization_id WHERE u.email=?",
        (email,),
    ).fetchone()
    if not row or row["status"] != "active" or row["organization_status"] != "active":
        hash_password("timing-equalizer-password")
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    connection.execute("UPDATE users SET last_login_at=? WHERE id=?", (timestamp(), row["id"]))
    connection.commit()
    return _auth_user(row)


def _auth_user(row: sqlite3.Row) -> AuthUser:
    return AuthUser(
        id=row["id"], organization_id=row["organization_id"], email=row["email"],
        display_name=row["display_name"], company_name=row["company_name"],
        country=row["country"], registration_number=row["registration_number"],
        role=row["role"],
    )


def create_session(connection: sqlite3.Connection, user_id: int) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    csrf_token = secrets.token_urlsafe(24)
    created = now()
    connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (timestamp(created),))
    connection.execute(
        "INSERT INTO sessions (user_id,token_hash,csrf_token,created_at,expires_at,last_seen_at) VALUES (?,?,?,?,?,?)",
        (user_id, token_hash, csrf_token, timestamp(created), timestamp(created + SESSION_LIFETIME), timestamp(created)),
    )
    connection.commit()
    return raw_token, csrf_token


def user_for_session(connection: sqlite3.Connection, raw_token: str | None) -> tuple[AuthUser, str] | None:
    if not raw_token:
        return None
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    row = connection.execute(
        "SELECT u.id,u.organization_id,u.email,u.display_name,u.role,u.status,s.id session_id,s.csrf_token,s.expires_at,"
        "o.name company_name,o.country,o.registration_number,o.status organization_status "
        "FROM sessions s JOIN users u ON u.id=s.user_id JOIN organizations o ON o.id=u.organization_id "
        "WHERE s.token_hash=?",
        (token_hash,),
    ).fetchone()
    if not row or row["expires_at"] <= timestamp() or row["status"] != "active" or row["organization_status"] != "active":
        if row:
            connection.execute("DELETE FROM sessions WHERE id=?", (row["session_id"],))
            connection.commit()
        return None
    connection.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (timestamp(), row["session_id"]))
    connection.commit()
    return _auth_user(row), row["csrf_token"]


def delete_session(connection: sqlite3.Connection, raw_token: str | None) -> None:
    if raw_token:
        connection.execute(
            "DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(raw_token.encode()).hexdigest(),)
        )
        connection.commit()


def public_user(user: AuthUser, csrf_token: str) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "organization": {
            "id": user.organization_id,
            "name": user.company_name,
            "country": user.country,
            "registration_number": user.registration_number,
        },
        "csrf_token": csrf_token,
        "role": user.role,
    }


def create_request(
    connection: sqlite3.Connection,
    user: AuthUser,
    payload: dict[str, Any],
    product_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_type = str(payload.get("request_type") or "").casefold()
    if request_type not in REQUEST_TYPES:
        raise PortalError("Request type must be stock or wanted.")
    try:
        quantity = float(payload.get("quantity"))
    except (TypeError, ValueError):
        raise PortalError("Quantity must be a number.") from None
    if quantity <= 0 or quantity > 1_000_000_000:
        raise PortalError("Quantity must be greater than zero.")
    target_value = payload.get("target_price")
    target_price = None
    if target_value not in (None, ""):
        try:
            target_price = float(target_value)
        except (TypeError, ValueError):
            raise PortalError("Target price must be a number.") from None
        if target_price < 0:
            raise PortalError("Target price cannot be negative.")
    destination = required_text(payload.get("destination"), "Destination", 200)
    brand = optional_text(payload.get("brand"), 200)
    category = optional_text(payload.get("category"), 200)
    currency = optional_text(payload.get("currency"), 3)
    notes = optional_text(payload.get("notes"), 2_000)
    product_id = payload.get("product_id")
    if request_type == "stock" and (not isinstance(product_id, int) or not product_snapshot):
        raise PortalError("Select a valid catalogue product.")
    if request_type == "wanted" and not (brand or category):
        raise PortalError("Provide a brand or category for wanted stock.")
    created = timestamp()
    cursor = connection.execute(
        "INSERT INTO demand_requests (organization_id,created_by,request_type,product_id,product_snapshot_json,brand,category,quantity,target_price,currency,destination,notes,created_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            user.organization_id, user.id, request_type, product_id,
            json.dumps(product_snapshot, separators=(",", ":")) if product_snapshot else None,
            brand, category, quantity, target_price, currency.upper() if currency else None,
            destination, notes, created, created,
        ),
    )
    request_id = int(cursor.lastrowid)
    reference = f"DR-{request_id:06d}"
    connection.execute("UPDATE demand_requests SET reference=? WHERE id=?", (reference, request_id))
    connection.execute(
        "INSERT INTO request_status_history (request_id,status,note,changed_by,created_at) VALUES (?,?,?,?,?)",
        (request_id, "new", "Request submitted", user.id, created),
    )
    queue_email(
        connection,
        user.email,
        f"Demand request {reference} received",
        f"We received your demand request {reference}. It is now in the trading desk queue.",
    )
    queue_email(
        connection,
        os.environ.get("STRAIIT_OPERATOR_EMAIL", "sales@straiit.trade"),
        f"New demand request {reference}",
        f"{user.company_name} submitted {reference} for quantity {quantity:g}.",
    )
    connection.commit()
    return get_request(connection, user, request_id)


def _serialize_request(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    snapshot = item.pop("product_snapshot_json", None)
    item["product"] = json.loads(snapshot) if snapshot else None
    item["quote"] = None
    if item.get("quote_id"):
        item["quote"] = {
            "id": item.pop("quote_id"), "amount": item.pop("quote_amount"),
            "currency": item.pop("quote_currency"), "valid_until": item.pop("quote_valid_until"),
            "terms": item.pop("quote_terms"), "status": item.pop("quote_status"),
        }
        item["reservation"] = None
        if item.get("reservation_id"):
            item["reservation"] = {
                "id": item.pop("reservation_id"), "quantity": item.pop("reservation_quantity"),
                "status": item.pop("reservation_status"), "expires_at": item.pop("reservation_expires_at"),
            }
        else:
            for key in ("reservation_id", "reservation_quantity", "reservation_status", "reservation_expires_at"):
                item.pop(key, None)
    else:
        item["reservation"] = None
        for key in ("quote_id", "quote_amount", "quote_currency", "quote_valid_until", "quote_terms", "quote_status", "reservation_id", "reservation_quantity", "reservation_status", "reservation_expires_at"):
            item.pop(key, None)
    return item


REQUEST_SELECT = """
SELECT r.*,q.id quote_id,q.amount quote_amount,q.currency quote_currency,
       q.valid_until quote_valid_until,q.terms quote_terms,q.status quote_status,
       z.id reservation_id,z.quantity reservation_quantity,z.status reservation_status,z.expires_at reservation_expires_at
FROM demand_requests r
LEFT JOIN quotes q ON q.id=(SELECT id FROM quotes WHERE request_id=r.id ORDER BY id DESC LIMIT 1)
LEFT JOIN reservations z ON z.id=(SELECT id FROM reservations WHERE quote_id=q.id ORDER BY id DESC LIMIT 1)
"""


def get_request(connection: sqlite3.Connection, user: AuthUser, request_id: int) -> dict[str, Any]:
    row = connection.execute(
        REQUEST_SELECT + " WHERE r.id=? AND r.organization_id=?", (request_id, user.organization_id)
    ).fetchone()
    if not row:
        raise PortalError("Request not found.")
    item = _serialize_request(row)
    item["history"] = [dict(history) for history in connection.execute(
        "SELECT status,note,created_at FROM request_status_history WHERE request_id=? ORDER BY id DESC",
        (request_id,),
    )]
    return item


def list_requests(connection: sqlite3.Connection, user: AuthUser) -> list[dict[str, Any]]:
    return [
        _serialize_request(row) for row in connection.execute(
            REQUEST_SELECT + " WHERE r.organization_id=? ORDER BY r.created_at DESC, r.id DESC",
            (user.organization_id,),
        )
    ]


def list_all_requests(connection: sqlite3.Connection, status: str | None = None) -> list[dict[str, Any]]:
    params: tuple[Any, ...] = ()
    where = ""
    if status:
        if status not in REQUEST_STATUSES:
            raise PortalError("Unknown request status.")
        where = " WHERE r.status=?"
        params = (status,)
    rows = connection.execute(
        "SELECT r.id,r.reference,r.request_type,r.product_id,r.brand,r.category,r.quantity,r.target_price,"
        "r.currency,r.destination,r.status,r.created_at,r.updated_at,o.name organization_name,u.email created_by_email "
        "FROM demand_requests r JOIN organizations o ON o.id=r.organization_id "
        "JOIN users u ON u.id=r.created_by" + where + " ORDER BY r.created_at DESC,r.id DESC",
        params,
    )
    return [dict(row) for row in rows]


def set_request_status(
    connection: sqlite3.Connection,
    reference: str,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    status = status.casefold()
    if status not in REQUEST_STATUSES:
        raise PortalError("Unknown request status.")
    row = connection.execute(
        "SELECT r.id,u.email FROM demand_requests r JOIN users u ON u.id=r.created_by WHERE r.reference=?",
        (reference.upper(),),
    ).fetchone()
    if not row:
        raise PortalError("Request not found.")
    changed = timestamp()
    connection.execute(
        "UPDATE demand_requests SET status=?,updated_at=? WHERE id=?", (status, changed, row["id"])
    )
    queue_email(
        connection, row["email"], f"Demand request {reference.upper()} updated",
        f"Your demand request is now {status.replace('_', ' ')}." + (f"\n\n{note}" if note else ""),
    )
    connection.execute(
        "INSERT INTO request_status_history (request_id,status,note,created_at) VALUES (?,?,?,?)",
        (row["id"], status, optional_text(note, 500), changed),
    )
    connection.commit()
    return {"reference": reference.upper(), "status": status, "updated_at": changed}


def issue_quote(
    connection: sqlite3.Connection,
    reference: str,
    amount: float,
    currency: str,
    valid_until: str | None = None,
    terms: str | None = None,
) -> dict[str, Any]:
    if amount <= 0:
        raise PortalError("Quote amount must be greater than zero.")
    currency = required_text(currency, "Currency", 3).upper()
    row = connection.execute(
        "SELECT r.id,u.email FROM demand_requests r JOIN users u ON u.id=r.created_by WHERE r.reference=?",
        (reference.upper(),),
    ).fetchone()
    if not row:
        raise PortalError("Request not found.")
    created = timestamp()
    quote_id = connection.execute(
        "INSERT INTO quotes (request_id,amount,currency,valid_until,terms,created_at) VALUES (?,?,?,?,?,?)",
        (row["id"], amount, currency, optional_text(valid_until, 40), optional_text(terms, 2_000), created),
    ).lastrowid
    connection.execute(
        "UPDATE demand_requests SET status='quoted',updated_at=? WHERE id=?", (created, row["id"])
    )
    queue_email(
        connection, row["email"], f"Quote issued for {reference.upper()}",
        f"A quote for {amount:g} {currency} is ready. Sign in to review, reserve the stock, and pay securely.",
    )
    connection.execute(
        "INSERT INTO request_status_history (request_id,status,note,created_at) VALUES (?,?,?,?)",
        (row["id"], "quoted", f"Quote {quote_id} issued", created),
    )
    connection.commit()
    return {
        "id": quote_id, "reference": reference.upper(), "amount": amount,
        "currency": currency, "valid_until": valid_until, "status": "open",
    }


def queue_email(connection: sqlite3.Connection, to_email: str, subject: str, body: str) -> int:
    return int(connection.execute(
        "INSERT INTO email_outbox (to_email,subject,text_body,created_at) VALUES (?,?,?,?)",
        (normalize_email(to_email), required_text(subject, "Subject", 200), body.strip(), timestamp()),
    ).lastrowid)


def create_operator(
    connection: sqlite3.Connection, email_value: Any, password_value: Any, display_name: str | None = None
) -> dict[str, Any]:
    email = normalize_email(email_value)
    password = validate_password(password_value)
    if connection.execute("SELECT 1 FROM users WHERE email=?", (email,)).fetchone():
        raise ConflictError("An account already exists for this email.")
    organization = connection.execute(
        "SELECT id FROM organizations WHERE name=?", ("Straiit Trading Desk",)
    ).fetchone()
    organization_id = organization["id"] if organization else connection.execute(
        "INSERT INTO organizations (name,country) VALUES (?,?)", ("Straiit Trading Desk", "United Kingdom")
    ).lastrowid
    user_id = connection.execute(
        "INSERT INTO users (organization_id,email,password_hash,display_name,role) VALUES (?,?,?,?, 'operator')",
        (organization_id, email, hash_password(password), optional_text(display_name, 120)),
    ).lastrowid
    connection.commit()
    return {"id": user_id, "email": email, "role": "operator"}


def request_password_reset(
    connection: sqlite3.Connection, email_value: Any, public_url: str
) -> None:
    try:
        email = normalize_email(email_value)
    except PortalError:
        return
    row = connection.execute(
        "SELECT id,email FROM users WHERE email=? AND status='active'", (email,)
    ).fetchone()
    if row:
        raw_token = secrets.token_urlsafe(32)
        created = now()
        connection.execute(
            "UPDATE password_reset_tokens SET used_at=? WHERE user_id=? AND used_at IS NULL",
            (timestamp(created), row["id"]),
        )
        connection.execute(
            "INSERT INTO password_reset_tokens (user_id,token_hash,created_at,expires_at) VALUES (?,?,?,?)",
            (
                row["id"], hashlib.sha256(raw_token.encode()).hexdigest(), timestamp(created),
                timestamp(created + RESET_LIFETIME),
            ),
        )
        reset_url = f"{public_url.rstrip('/')}/reset-password?token={raw_token}"
        queue_email(
            connection, row["email"], "Reset your Straiit password",
            f"Use this one-time link within 30 minutes to reset your password:\n\n{reset_url}\n\nIf you did not request this, you can ignore this email.",
        )
    connection.commit()


def reset_password(connection: sqlite3.Connection, raw_token: Any, new_password: Any) -> None:
    token = required_text(raw_token, "Reset token", 500)
    password = validate_password(new_password)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    connection.execute("BEGIN IMMEDIATE")
    row = connection.execute(
        "SELECT id,user_id,expires_at,used_at FROM password_reset_tokens WHERE token_hash=?", (token_hash,)
    ).fetchone()
    if not row or row["used_at"] or row["expires_at"] <= timestamp():
        connection.rollback()
        raise PortalError("This password reset link is invalid or has expired.")
    changed = timestamp()
    connection.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), row["user_id"]))
    connection.execute("UPDATE password_reset_tokens SET used_at=? WHERE id=?", (changed, row["id"]))
    connection.execute("DELETE FROM sessions WHERE user_id=?", (row["user_id"],))
    email = connection.execute("SELECT email FROM users WHERE id=?", (row["user_id"],)).fetchone()["email"]
    queue_email(connection, email, "Your Straiit password was changed", "Your password has been reset. All existing sessions were signed out.")
    connection.commit()


def expire_reservations(connection: sqlite3.Connection, *, commit: bool = True) -> int:
    expired_at = timestamp()
    rows = connection.execute(
        "SELECT id,request_id,quote_id FROM reservations WHERE status='held' AND expires_at<=?", (expired_at,)
    ).fetchall()
    for row in rows:
        connection.execute("UPDATE reservations SET status='expired',updated_at=? WHERE id=?", (expired_at, row["id"]))
        connection.execute("UPDATE quotes SET status='open' WHERE id=? AND status='accepted'", (row["quote_id"],))
        connection.execute("UPDATE demand_requests SET status='quoted',updated_at=? WHERE id=?", (expired_at, row["request_id"]))
        connection.execute(
            "INSERT INTO request_status_history (request_id,status,note,created_at) VALUES (?,?,?,?)",
            (row["request_id"], "quoted", "Unpaid stock hold expired", expired_at),
        )
    if commit:
        connection.commit()
    return len(rows)


def reserved_quantity(connection: sqlite3.Connection, product_id: int) -> float:
    expire_reservations(connection)
    row = connection.execute(
        "SELECT COALESCE(SUM(quantity),0) total FROM reservations WHERE product_id=? AND status IN ('held','confirmed')",
        (product_id,),
    ).fetchone()
    return float(row["total"])


def reservation_totals(connection: sqlite3.Connection, product_ids: list[int]) -> dict[int, float]:
    expire_reservations(connection)
    ids = sorted(set(product_ids))
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    return {
        int(row["product_id"]): float(row["total"])
        for row in connection.execute(
            f"SELECT product_id,SUM(quantity) total FROM reservations WHERE status IN ('held','confirmed') AND product_id IN ({placeholders}) GROUP BY product_id",
            ids,
        )
    }


def hold_stock(
    connection: sqlite3.Connection,
    reference: str,
    catalogue_quantity: float | None,
    changed_by: int | None = None,
) -> dict[str, Any]:
    if catalogue_quantity is None:
        raise PortalError("This product has no confirmed stock quantity and cannot be reserved.")
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    expire_reservations(connection, commit=False)
    row = connection.execute(
        "SELECT r.id request_id,r.reference,r.organization_id,r.product_id,r.quantity,r.status,q.id quote_id,q.amount,q.currency,q.valid_until,q.status quote_status "
        "FROM demand_requests r JOIN quotes q ON q.id=(SELECT id FROM quotes WHERE request_id=r.id ORDER BY id DESC LIMIT 1) "
        "WHERE r.reference=? AND r.request_type='stock'",
        (reference.upper(),),
    ).fetchone()
    if not row:
        connection.rollback()
        raise PortalError("A quoted stock request was not found.")
    existing = connection.execute(
        "SELECT id,quantity,status,expires_at FROM reservations WHERE request_id=? AND status IN ('held','confirmed') ORDER BY id DESC LIMIT 1",
        (row["request_id"],),
    ).fetchone()
    if existing:
        connection.commit()
        return dict(existing)
    if row["quote_status"] != "open":
        connection.rollback()
        raise PortalError("This quote is no longer available for reservation.")
    if row["valid_until"] and row["valid_until"][:10] < now().date().isoformat():
        connection.execute("UPDATE quotes SET status='expired' WHERE id=?", (row["quote_id"],))
        connection.commit()
        raise PortalError("This quote has expired.")
    allocated = connection.execute(
        "SELECT COALESCE(SUM(quantity),0) total FROM reservations WHERE product_id=? AND status IN ('held','confirmed')",
        (row["product_id"],),
    ).fetchone()["total"]
    if float(row["quantity"]) > max(0.0, float(catalogue_quantity) - float(allocated)):
        connection.rollback()
        raise ConflictError("There is not enough unreserved stock to fulfil this request.")
    created = now()
    if row["valid_until"]:
        expires_at = f"{row['valid_until'][:10]}T23:59:59+00:00"
    else:
        expires_at = timestamp(created + timedelta(days=7))
    reservation_id = connection.execute(
        "INSERT INTO reservations (request_id,quote_id,product_id,organization_id,quantity,expires_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (row["request_id"], row["quote_id"], row["product_id"], row["organization_id"], row["quantity"], expires_at, timestamp(created), timestamp(created)),
    ).lastrowid
    connection.execute("UPDATE quotes SET status='accepted' WHERE id=?", (row["quote_id"],))
    connection.execute("UPDATE demand_requests SET status='accepted',updated_at=? WHERE id=?", (timestamp(created), row["request_id"]))
    connection.execute(
        "INSERT INTO request_status_history (request_id,status,note,changed_by,created_at) VALUES (?,?,?,?,?)",
        (row["request_id"], "accepted", "Stock held pending offline payment", changed_by, timestamp(created)),
    )
    buyer = connection.execute("SELECT email FROM users WHERE id=(SELECT created_by FROM demand_requests WHERE id=?)", (row["request_id"],)).fetchone()
    queue_email(connection, buyer["email"], f"Stock held for {row['reference']}", f"The trading desk has reserved the requested stock until {expires_at}. Follow the quoted payment terms to complete the order.")
    connection.commit()
    return {
        "id": reservation_id, "request_id": row["request_id"], "quote_id": row["quote_id"],
        "reference": row["reference"], "quantity": row["quantity"], "expires_at": expires_at, "status": "held",
    }


def confirm_reservation(connection: sqlite3.Connection, reservation_id: int, note: str | None = None) -> dict[str, Any]:
    expire_reservations(connection)
    changed = timestamp()
    row = connection.execute(
        "SELECT z.*,r.reference,u.email FROM reservations z JOIN demand_requests r ON r.id=z.request_id JOIN users u ON u.id=r.created_by WHERE z.id=?",
        (reservation_id,),
    ).fetchone()
    if not row or row["status"] != "held":
        raise PortalError("Held reservation not found.")
    connection.execute("UPDATE reservations SET status='confirmed',expires_at=NULL,updated_at=? WHERE id=?", (changed, reservation_id))
    message = optional_text(note, 500) or "Offline payment confirmed; reservation is firm"
    connection.execute("INSERT INTO request_status_history (request_id,status,note,created_at) VALUES (?,?,?,?)", (row["request_id"], "accepted", message, changed))
    queue_email(connection, row["email"], f"Reservation confirmed for {row['reference']}", "The trading desk has confirmed payment and your stock reservation is now firm. We will contact you about fulfilment.")
    connection.commit()
    return {"id": reservation_id, "reference": row["reference"], "status": "confirmed"}


def release_reservation(connection: sqlite3.Connection, reservation_id: int, note: str | None = None) -> dict[str, Any]:
    row = connection.execute(
        "SELECT z.*,r.reference,u.email FROM reservations z JOIN demand_requests r ON r.id=z.request_id JOIN users u ON u.id=r.created_by WHERE z.id=?",
        (reservation_id,),
    ).fetchone()
    if not row or row["status"] not in {"held", "confirmed"}:
        raise PortalError("Active reservation not found.")
    changed = timestamp()
    connection.execute("UPDATE reservations SET status='released',updated_at=? WHERE id=?", (changed, reservation_id))
    connection.execute("UPDATE demand_requests SET status='closed',updated_at=? WHERE id=?", (changed, row["request_id"]))
    connection.execute("INSERT INTO request_status_history (request_id,status,note,created_at) VALUES (?,?,?,?)", (row["request_id"], "closed", optional_text(note, 500) or "Stock reservation released", changed))
    queue_email(connection, row["email"], f"Reservation released for {row['reference']}", optional_text(note, 500) or "The stock reservation has been released. Contact the trading desk if you need help.")
    connection.commit()
    return {"id": reservation_id, "reference": row["reference"], "status": "released"}


def admin_overview(connection: sqlite3.Connection) -> dict[str, Any]:
    expire_reservations(connection)
    applications = [dict(row) for row in connection.execute(
        "SELECT id,company_name,registration_number,country,email,status,created_at,reviewed_at,review_note FROM account_applications ORDER BY created_at DESC LIMIT 100"
    )]
    requests = list_all_requests(connection)
    reservations = [dict(row) for row in connection.execute(
        "SELECT z.id,z.quantity,z.status,z.expires_at,z.created_at,r.reference,r.product_id,o.name organization_name "
        "FROM reservations z JOIN demand_requests r ON r.id=z.request_id JOIN organizations o ON o.id=z.organization_id "
        "ORDER BY z.created_at DESC LIMIT 100"
    )]
    outbox = [dict(row) for row in connection.execute(
        "SELECT id,to_email,subject,status,attempts,last_error,created_at,sent_at FROM email_outbox ORDER BY created_at DESC LIMIT 50"
    )]
    return {"applications": applications, "requests": requests, "reservations": reservations, "emails": outbox}
