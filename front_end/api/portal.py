from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


PORTAL_DATABASE = Path(__file__).resolve().parent / "portal.db"
PASSWORD_ITERATIONS = 600_000
SESSION_LIFETIME = timedelta(days=7)
REQUEST_TYPES = {"stock", "wanted"}
REQUEST_STATUSES = {"new", "reviewing", "sourcing", "quoted", "accepted", "closed", "rejected"}


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
    with connect_portal(database, use_wal=False) as connection:
        connection.executescript(SCHEMA)


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
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    return {"application_id": application_id, "organization_id": organization_id, "user_id": user_id}


def reject_application(connection: sqlite3.Connection, application_id: int, note: str | None = None) -> None:
    cursor = connection.execute(
        "UPDATE account_applications SET status='rejected',reviewed_at=?,review_note=? WHERE id=? AND status='pending'",
        (timestamp(), optional_text(note, 500), application_id),
    )
    if cursor.rowcount != 1:
        raise PortalError("Pending application not found.")
    connection.commit()


def authenticate(connection: sqlite3.Connection, email_value: Any, password_value: Any) -> AuthUser | None:
    try:
        email = normalize_email(email_value)
    except PortalError:
        return None
    password = str(password_value or "")
    row = connection.execute(
        "SELECT u.id,u.organization_id,u.email,u.password_hash,u.display_name,u.status,"
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
        "SELECT u.id,u.organization_id,u.email,u.display_name,u.status,s.id session_id,s.csrf_token,s.expires_at,"
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
    else:
        for key in ("quote_id", "quote_amount", "quote_currency", "quote_valid_until", "quote_terms", "quote_status"):
            item.pop(key, None)
    return item


REQUEST_SELECT = """
SELECT r.*,q.id quote_id,q.amount quote_amount,q.currency quote_currency,
       q.valid_until quote_valid_until,q.terms quote_terms,q.status quote_status
FROM demand_requests r
LEFT JOIN quotes q ON q.id=(SELECT id FROM quotes WHERE request_id=r.id ORDER BY id DESC LIMIT 1)
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
    row = connection.execute("SELECT id FROM demand_requests WHERE reference=?", (reference.upper(),)).fetchone()
    if not row:
        raise PortalError("Request not found.")
    changed = timestamp()
    connection.execute(
        "UPDATE demand_requests SET status=?,updated_at=? WHERE id=?", (status, changed, row["id"])
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
    row = connection.execute("SELECT id FROM demand_requests WHERE reference=?", (reference.upper(),)).fetchone()
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
    connection.execute(
        "INSERT INTO request_status_history (request_id,status,note,created_at) VALUES (?,?,?,?)",
        (row["id"], "quoted", f"Quote {quote_id} issued", created),
    )
    connection.commit()
    return {
        "id": quote_id, "reference": reference.upper(), "amount": amount,
        "currency": currency, "valid_until": valid_until, "status": "open",
    }
