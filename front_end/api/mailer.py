from __future__ import annotations

import os
import smtplib
import sqlite3
import ssl
import threading
from email.message import EmailMessage
from pathlib import Path

try:
    from .portal import PORTAL_DATABASE, connect_portal, timestamp
    from .database import DatabaseError
except ImportError:  # Support direct script entry points.
    from portal import PORTAL_DATABASE, connect_portal, timestamp
    from database import DatabaseError


def smtp_configured() -> bool:
    return bool(os.environ.get("STRAIIT_SMTP_HOST"))


def send_pending_emails(database: Path = PORTAL_DATABASE, limit: int = 20) -> dict[str, int]:
    if not smtp_configured():
        return {"sent": 0, "failed": 0, "queued": 0}
    with connect_portal(database) as connection:
        rows = connection.execute(
            "SELECT id,to_email,subject,text_body FROM email_outbox WHERE status IN ('queued','failed') AND attempts<5 ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
    sent = failed = 0
    for row in rows:
        with connect_portal(database) as connection:
            claimed = connection.execute(
                "UPDATE email_outbox SET status='sending',attempts=attempts+1 WHERE id=? AND status IN ('queued','failed')",
                (row["id"],),
            )
            connection.commit()
        if claimed.rowcount != 1:
            continue
        try:
            _send(row["to_email"], row["subject"], row["text_body"])
        except (OSError, smtplib.SMTPException) as error:
            with connect_portal(database) as connection:
                connection.execute(
                    "UPDATE email_outbox SET status='failed',last_error=? WHERE id=?",
                    (str(error)[:500], row["id"]),
                )
                connection.commit()
            failed += 1
        else:
            with connect_portal(database) as connection:
                connection.execute(
                    "UPDATE email_outbox SET status='sent',sent_at=?,last_error=NULL,text_body='[delivered]' WHERE id=?",
                    (timestamp(), row["id"]),
                )
                connection.commit()
            sent += 1
    return {"sent": sent, "failed": failed, "queued": len(rows)}


def _send(to_email: str, subject: str, body: str) -> None:
    host = os.environ["STRAIIT_SMTP_HOST"]
    port = int(os.environ.get("STRAIIT_SMTP_PORT", "587"))
    username = os.environ.get("STRAIIT_SMTP_USERNAME")
    password = os.environ.get("STRAIIT_SMTP_PASSWORD")
    sender = os.environ.get("STRAIIT_EMAIL_FROM", "Straiit Stock <sales@straiit.trade>")
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    use_ssl = os.environ.get("STRAIIT_SMTP_SSL", "").lower() in {"1", "true", "yes"}
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    with smtp_class(host, port, timeout=20) as client:
        if not use_ssl and os.environ.get("STRAIIT_SMTP_STARTTLS", "1").lower() not in {"0", "false", "no"}:
            client.starttls(context=ssl.create_default_context())
        if username:
            client.login(username, password or "")
        client.send_message(message)


class EmailDispatcher(threading.Thread):
    def __init__(self, database: Path, interval_seconds: int = 15):
        super().__init__(name="straiit-email-dispatcher", daemon=True)
        self.database = database
        self.interval_seconds = interval_seconds
        self.stopped = threading.Event()

    def run(self) -> None:
        while not self.stopped.is_set():
            try:
                send_pending_emails(self.database)
            except (sqlite3.Error, DatabaseError):
                pass
            self.stopped.wait(self.interval_seconds)
