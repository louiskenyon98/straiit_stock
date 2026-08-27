from __future__ import annotations

import os
import re
import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


class DatabaseError(RuntimeError):
    """Database error with a backend-independent public type."""


RUNTIME_CONFIG = Path(__file__).resolve().parent / "runtime.local.json"


class CompatRow(dict[str, Any]):
    """Mapping row that also supports SQLite-style numeric indexing."""

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class CompatCursor:
    def __init__(self, cursor: Any, *, lastrowid: int | None = None):
        self.cursor = cursor
        self.lastrowid = lastrowid

    @property
    def rowcount(self) -> int:
        return int(self.cursor.rowcount)

    @staticmethod
    def _row(value: Any) -> CompatRow | None:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return CompatRow(value)
        raise DatabaseError("PostgreSQL returned an unexpected row format.")

    def fetchone(self) -> CompatRow | None:
        return self._row(self.cursor.fetchone())

    def fetchall(self) -> list[CompatRow]:
        return [self._row(row) for row in self.cursor.fetchall() if row is not None]

    def __iter__(self) -> Iterator[CompatRow]:
        for row in self.cursor:
            converted = self._row(row)
            if converted is not None:
                yield converted


INSERT_PATTERN = re.compile(r"^\s*INSERT\s+INTO\s+", re.IGNORECASE)


def runtime_config() -> dict[str, Any]:
    if not RUNTIME_CONFIG.is_file():
        return {}
    try:
        configured = json.loads(RUNTIME_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DatabaseError(f"Invalid runtime configuration: {RUNTIME_CONFIG}") from error
    if not isinstance(configured, dict):
        raise DatabaseError(f"Runtime configuration must be a JSON object: {RUNTIME_CONFIG}")
    return configured


def postgres_url() -> str | None:
    """Return the URL from the environment or the ignored local runtime file."""

    value = (
        runtime_config().get("neon_database_url")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("NEON_DATABASE_URL")
        or os.environ.get("NEON_DIRECT_DATABASE_URL")
        or ""
    )
    if not isinstance(value, str):
        raise DatabaseError("neon_database_url must be a string.")
    value = value.strip()
    return value or None


def media_base_url() -> str | None:
    """Return the optional public origin used for catalogue media."""

    value = (
        runtime_config().get("media_base_url")
        or os.environ.get("STRAIIT_MEDIA_BASE_URL")
        or ""
    )
    if not isinstance(value, str):
        raise DatabaseError("media_base_url must be a string.")
    value = value.strip().rstrip("/")
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DatabaseError("media_base_url must be an absolute HTTP or HTTPS URL.")
    return value


def using_postgres() -> bool:
    override = os.environ.get("STRAIIT_USE_NEON")
    if override is not None:
        normalized = override.strip().casefold()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        raise DatabaseError("STRAIIT_USE_NEON must be true or false.")
    configured = runtime_config()
    if configured:
        value = configured.get("use_neon")
        if not isinstance(value, bool):
            raise DatabaseError(
                f"Runtime configuration must contain a boolean use_neon value: {RUNTIME_CONFIG}"
            )
        return value
    return postgres_url() is not None


def safe_database_label() -> str:
    value = postgres_url()
    if not value:
        return "SQLite"
    parsed = urlparse(value)
    database = parsed.path.lstrip("/") or "unknown"
    return f"PostgreSQL database {database} at {parsed.hostname or 'unknown host'}"


def postgres_sql(statement: str) -> str:
    """Translate the small SQLite parameter subset used by this application."""

    return statement.replace("?", "%s")


class PostgresConnection:
    is_postgres = True

    def __init__(self, connection: Any):
        self.connection = connection

    def _ensure_search_path(self) -> None:
        try:
            from psycopg.pq import TransactionStatus

            if self.connection.info.transaction_status == TransactionStatus.IDLE:
                self.connection.execute(
                    "SET LOCAL search_path TO catalogue, portal, public"
                )
        except Exception as error:
            self._raise_database_error(error)

    @staticmethod
    def _raise_database_error(error: Exception) -> None:
        try:
            import psycopg

            if isinstance(error, psycopg.Error):
                raise DatabaseError(str(error)) from error
        except ImportError:
            pass
        raise error

    def execute(
        self, statement: str, parameters: Sequence[Any] | None = None
    ) -> CompatCursor:
        normalized = statement.strip().upper()
        if normalized == "BEGIN IMMEDIATE":
            self._ensure_search_path()
            return CompatCursor(self.connection.cursor())
        self._ensure_search_path()
        query = postgres_sql(statement)
        returns_id = bool(INSERT_PATTERN.match(query)) and " RETURNING " not in query.upper()
        if returns_id:
            query = query.rstrip().rstrip(";") + " RETURNING id"
        try:
            cursor = self.connection.execute(query, parameters or ())
            lastrowid = None
            if returns_id:
                returned = cursor.fetchone()
                if returned is not None:
                    lastrowid = int(returned["id"])
            return CompatCursor(cursor, lastrowid=lastrowid)
        except Exception as error:
            self._raise_database_error(error)
            raise AssertionError("unreachable")

    def commit(self) -> None:
        try:
            self.connection.commit()
        except Exception as error:
            self._raise_database_error(error)

    def rollback(self) -> None:
        try:
            self.connection.rollback()
        except Exception as error:
            self._raise_database_error(error)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> PostgresConnection:
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        if exception_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()


def connect_postgres() -> PostgresConnection:
    value = postgres_url()
    if not value:
        raise DatabaseError("DATABASE_URL is not configured.")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise DatabaseError(
            'PostgreSQL driver missing. Run: python -m pip install -r api/requirements.txt'
        ) from error
    try:
        return PostgresConnection(psycopg.connect(value, row_factory=dict_row))
    except psycopg.Error as error:
        raise DatabaseError(str(error)) from error
