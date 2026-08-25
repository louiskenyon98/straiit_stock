from __future__ import annotations

import hmac
import json
import mimetypes
import os
import sqlite3
import time
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from urllib.parse import parse_qs, unquote, urlparse

from catalogue import (
    DEFAULT_DATABASE,
    DEFAULT_MEDIA_ROOT,
    ProductQuery,
    connect,
    facets,
    get_product,
    list_products,
    related_products,
    summary,
)
from portal import (
    PORTAL_DATABASE,
    ConflictError,
    PortalError,
    authenticate,
    connect_portal,
    create_request,
    create_session,
    delete_session,
    ensure_schema,
    list_requests,
    public_user,
    submit_application,
    user_for_session,
)


DATABASE = Path(os.environ.get("STRAIIT_DATABASE", DEFAULT_DATABASE)).resolve()
MEDIA_ROOT = Path(os.environ.get("STRAIIT_MEDIA_ROOT", DEFAULT_MEDIA_ROOT)).resolve()
PORTAL_DB = Path(os.environ.get("STRAIIT_PORTAL_DATABASE", PORTAL_DATABASE)).resolve()
COOKIE_SECURE = os.environ.get("STRAIIT_COOKIE_SECURE", "").lower() in {"1", "true", "yes"}
ALLOWED_ORIGINS = {
    origin.strip().rstrip("/")
    for origin in os.environ.get(
        "STRAIIT_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
}
LOGIN_ATTEMPTS: dict[str, list[float]] = {}
LOGIN_LOCK = Lock()
LOGIN_WINDOW_SECONDS = 10 * 60
LOGIN_MAX_ATTEMPTS = 8


def first(params: dict[str, list[str]], key: str, default: str = "") -> str:
    return params.get(key, [default])[0]


def integer(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class Handler(BaseHTTPRequestHandler):
    server_version = "StraiitPortal/0.2"

    def _headers(
        self,
        status: HTTPStatus,
        content_type: str,
        length: int,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "public, max-age=86400")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()

    def json(
        self,
        payload,
        status: HTTPStatus = HTTPStatus.OK,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body), headers)
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path.startswith("/media/"):
                self.serve_media(parsed.path)
                return
            if not parsed.path.startswith("/api/"):
                self.json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
                return
            params = parse_qs(parsed.query)
            if parsed.path == "/api/auth/me":
                self.auth_me()
            elif parsed.path == "/api/requests":
                self.requests_list()
            else:
                with connect(DATABASE) as connection:
                    if parsed.path == "/api/health":
                        self.json({"status": "ok"})
                    elif parsed.path == "/api/catalogue/summary":
                        self.json(summary(connection))
                    elif parsed.path == "/api/catalogue/facets":
                        self.json(facets(connection))
                    elif parsed.path == "/api/products":
                        query = ProductQuery(
                            page=integer(first(params, "page", "1"), 1),
                            page_size=integer(first(params, "page_size", "24"), 24),
                            query=first(params, "query"),
                            brand=first(params, "brand"),
                            category=first(params, "category"),
                            status=first(params, "status"),
                            gender=first(params, "gender"),
                            currency=first(params, "currency"),
                            in_stock=first(params, "in_stock").lower() in {"1", "true", "yes"},
                            sort=first(params, "sort", "name"),
                        )
                        self.json(list_products(connection, query))
                    elif parsed.path.startswith("/api/products/"):
                        self.product_route(connection, parsed.path)
                    else:
                        self.json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except (sqlite3.Error, OSError, json.JSONDecodeError) as error:
            self.log_error("Request failed: %s", error)
            self.json({"error": "Service unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self.valid_origin():
            self.json({"error": "Request origin is not allowed"}, HTTPStatus.FORBIDDEN)
            return
        try:
            payload = self.read_json()
            if parsed.path == "/api/auth/applications":
                with connect_portal(PORTAL_DB) as connection:
                    result = submit_application(connection, payload)
                self.json(result, HTTPStatus.CREATED)
            elif parsed.path == "/api/auth/login":
                self.login(payload)
            elif parsed.path == "/api/auth/logout":
                self.logout()
            elif parsed.path == "/api/requests":
                self.request_create(payload)
            else:
                self.json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        except ConflictError as error:
            self.json({"error": str(error)}, HTTPStatus.CONFLICT)
        except PortalError as error:
            self.json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        except json.JSONDecodeError:
            self.json({"error": "Request body must be valid JSON"}, HTTPStatus.BAD_REQUEST)
        except (sqlite3.Error, OSError) as error:
            self.log_error("Request failed: %s", error)
            self.json({"error": "Service unavailable"}, HTTPStatus.SERVICE_UNAVAILABLE)

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/media/"):
            self.serve_media(parsed.path, head_only=True)
            return
        self._headers(HTTPStatus.METHOD_NOT_ALLOWED, "text/plain; charset=utf-8", 0)

    def product_route(self, connection, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) not in {3, 4} or not parts[2].isdigit():
            self.json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        product_id = int(parts[2])
        if len(parts) == 4 and parts[3] == "related":
            self.json({"items": related_products(connection, product_id)})
            return
        if len(parts) != 3:
            self.json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        product = get_product(connection, product_id)
        if product is None:
            self.json({"error": "Product not found"}, HTTPStatus.NOT_FOUND)
            return
        self.json(product)

    def read_json(self) -> dict:
        length = integer(self.headers.get("Content-Length", "0"), 0)
        if length <= 0 or length > 64 * 1024:
            raise PortalError("Request body is missing or too large.")
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(payload, dict):
            raise PortalError("Request body must be a JSON object.")
        return payload

    def valid_origin(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin.rstrip("/") in ALLOWED_ORIGINS

    def session_token(self) -> str | None:
        cookie = SimpleCookie()
        cookie.load(self.headers.get("Cookie", ""))
        morsel = cookie.get("straiit_session")
        return morsel.value if morsel else None

    def authenticated(self, require_csrf: bool = False):
        with connect_portal(PORTAL_DB) as connection:
            session = user_for_session(connection, self.session_token())
        if not session:
            self.json({"error": "Authentication required"}, HTTPStatus.UNAUTHORIZED)
            return None
        user, csrf_token = session
        if require_csrf and not hmac.compare_digest(self.headers.get("X-CSRF-Token", ""), csrf_token):
            self.json({"error": "Invalid CSRF token"}, HTTPStatus.FORBIDDEN)
            return None
        return user, csrf_token

    def auth_me(self) -> None:
        auth = self.authenticated()
        if auth:
            self.json({"user": public_user(*auth)})

    def login_key(self, email: str) -> str:
        return f"{self.client_address[0]}:{email.strip().casefold()}"

    def login_limited(self, key: str, record: bool = False) -> bool:
        current = time.monotonic()
        with LOGIN_LOCK:
            if len(LOGIN_ATTEMPTS) > 10_000:
                for stored_key in list(LOGIN_ATTEMPTS):
                    if not any(current - value < LOGIN_WINDOW_SECONDS for value in LOGIN_ATTEMPTS[stored_key]):
                        LOGIN_ATTEMPTS.pop(stored_key, None)
            attempts = [value for value in LOGIN_ATTEMPTS.get(key, []) if current - value < LOGIN_WINDOW_SECONDS]
            if record:
                attempts.append(current)
            LOGIN_ATTEMPTS[key] = attempts
            return len(attempts) >= LOGIN_MAX_ATTEMPTS

    def login(self, payload: dict) -> None:
        email = str(payload.get("email") or "")
        key = self.login_key(email)
        if self.login_limited(key):
            self.json({"error": "Too many sign-in attempts. Try again later."}, HTTPStatus.TOO_MANY_REQUESTS)
            return
        with connect_portal(PORTAL_DB) as connection:
            user = authenticate(connection, email, payload.get("password"))
            if not user:
                self.login_limited(key, record=True)
                self.json({"error": "Email or password is incorrect."}, HTTPStatus.UNAUTHORIZED)
                return
            raw_token, csrf_token = create_session(connection, user.id)
        with LOGIN_LOCK:
            LOGIN_ATTEMPTS.pop(key, None)
        cookie = f"straiit_session={raw_token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={7 * 24 * 60 * 60}"
        if COOKIE_SECURE:
            cookie += "; Secure"
        self.json({"user": public_user(user, csrf_token)}, headers={"Set-Cookie": cookie})

    def logout(self) -> None:
        auth = self.authenticated(require_csrf=True)
        if not auth:
            return
        with connect_portal(PORTAL_DB) as connection:
            delete_session(connection, self.session_token())
        cookie = "straiit_session=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
        if COOKIE_SECURE:
            cookie += "; Secure"
        self.json({"status": "signed_out"}, headers={"Set-Cookie": cookie})

    def requests_list(self) -> None:
        auth = self.authenticated()
        if not auth:
            return
        with connect_portal(PORTAL_DB) as connection:
            items = list_requests(connection, auth[0])
        self.json({"items": items})

    def request_create(self, payload: dict) -> None:
        auth = self.authenticated(require_csrf=True)
        if not auth:
            return
        snapshot = None
        if str(payload.get("request_type") or "").casefold() == "stock":
            try:
                product_id = int(payload.get("product_id"))
            except (TypeError, ValueError):
                raise PortalError("Select a valid catalogue product.") from None
            payload["product_id"] = product_id
            with connect(DATABASE) as catalogue_connection:
                product = get_product(catalogue_connection, product_id)
            if product:
                snapshot = {
                    key: product.get(key)
                    for key in ("id", "brand", "name", "model", "sku", "category", "wholesale_price", "currency", "image_url")
                }
        with connect_portal(PORTAL_DB) as connection:
            item = create_request(connection, auth[0], payload, snapshot)
        self.json(item, HTTPStatus.CREATED)

    def serve_media(self, path: str, head_only: bool = False) -> None:
        relative = Path(unquote(path.removeprefix("/media/")).replace("/", os.sep))
        candidate = (MEDIA_ROOT / relative).resolve()
        try:
            candidate.relative_to(MEDIA_ROOT)
        except ValueError:
            self.json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
            return
        if not candidate.is_file():
            self.json({"error": "Image not found"}, HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        self._headers(HTTPStatus.OK, content_type, candidate.stat().st_size)
        if not head_only:
            self.wfile.write(candidate.read_bytes())

    def log_message(self, message: str, *args) -> None:
        print(f"{self.address_string()} - {message % args}")


if __name__ == "__main__":
    host = os.environ.get("STRAIIT_API_HOST", "127.0.0.1")
    port = int(os.environ.get("STRAIIT_API_PORT", "8787"))
    if not DATABASE.is_file():
        raise SystemExit(f"Database not found: {DATABASE}")
    ensure_schema(PORTAL_DB)
    print(f"Straiit catalogue API on http://{host}:{port}")
    print(f"Database: {DATABASE}")
    print(f"Portal database: {PORTAL_DB}")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
