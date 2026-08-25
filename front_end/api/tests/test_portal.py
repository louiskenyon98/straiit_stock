import sqlite3
import unittest
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import api.portal as portal


class PortalTests(unittest.TestCase):
    def setUp(self):
        self.original_iterations = portal.PASSWORD_ITERATIONS
        portal.PASSWORD_ITERATIONS = 1_000
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(portal.SCHEMA)

    def tearDown(self):
        self.connection.close()
        portal.PASSWORD_ITERATIONS = self.original_iterations

    def application(self, email="buyer@example.com", company="Import Co"):
        return portal.submit_application(self.connection, {
            "company": company,
            "registration_number": "VAT-123",
            "country": "United Kingdom",
            "email": email,
            "password": "a-secure-password",
        })

    def approved_user(self, email="buyer@example.com", company="Import Co"):
        application = self.application(email, company)
        portal.approve_application(self.connection, application["id"])
        return portal.authenticate(self.connection, email, "a-secure-password")

    def test_application_is_pending_until_approved(self):
        result = self.application()
        self.assertEqual(result["status"], "pending")
        self.assertIsNone(portal.authenticate(self.connection, "buyer@example.com", "a-secure-password"))
        portal.approve_application(self.connection, result["id"])
        self.assertEqual(portal.authenticate(self.connection, "buyer@example.com", "a-secure-password").company_name, "Import Co")

    def test_duplicate_pending_application_is_rejected(self):
        self.application()
        with self.assertRaises(portal.ConflictError):
            self.application()

    def test_session_is_hashed_and_revocable(self):
        user = self.approved_user()
        token, csrf = portal.create_session(self.connection, user.id)
        stored = self.connection.execute("SELECT token_hash FROM sessions").fetchone()[0]
        self.assertNotEqual(stored, token)
        self.assertEqual(portal.user_for_session(self.connection, token)[1], csrf)
        portal.delete_session(self.connection, token)
        self.assertIsNone(portal.user_for_session(self.connection, token))

    def test_stock_request_persists_snapshot_and_history(self):
        user = self.approved_user()
        request = portal.create_request(self.connection, user, {
            "request_type": "stock",
            "product_id": 42,
            "quantity": 500,
            "target_price": 12.5,
            "currency": "EUR",
            "destination": "Rotterdam",
            "notes": "Full size run preferred",
        }, {"id": 42, "brand": "Example", "sku": "SKU-42"})
        self.assertRegex(request["reference"], r"^DR-\d{6}$")
        self.assertEqual(request["product"]["sku"], "SKU-42")
        self.assertEqual(request["history"][0]["status"], "new")

    def test_requests_are_isolated_by_organization(self):
        first = self.approved_user()
        second = self.approved_user("second@example.com", "Second Co")
        portal.create_request(self.connection, first, {
            "request_type": "wanted", "brand": "Gucci", "quantity": 100,
            "destination": "London",
        })
        self.assertEqual(len(portal.list_requests(self.connection, first)), 1)
        self.assertEqual(len(portal.list_requests(self.connection, second)), 0)

    def test_wanted_request_requires_brand_or_category(self):
        user = self.approved_user()
        with self.assertRaises(portal.PortalError):
            portal.create_request(self.connection, user, {
                "request_type": "wanted", "quantity": 100, "destination": "London",
            })

    def test_trading_desk_can_issue_quote_and_update_status(self):
        user = self.approved_user()
        request = portal.create_request(self.connection, user, {
            "request_type": "wanted", "brand": "Gucci", "quantity": 100,
            "destination": "London",
        })
        quote = portal.issue_quote(
            self.connection, request["reference"], 3_500, "eur", "2026-09-30", "EXW",
        )
        refreshed = portal.list_requests(self.connection, user)[0]
        self.assertEqual(quote["currency"], "EUR")
        self.assertEqual(refreshed["status"], "quoted")
        self.assertEqual(refreshed["quote"]["amount"], 3_500)
        portal.set_request_status(self.connection, request["reference"], "accepted", "Buyer confirmed")
        self.assertEqual(portal.list_requests(self.connection, user)[0]["status"], "accepted")

    def test_operator_role_is_returned_in_session_identity(self):
        created = portal.create_operator(self.connection, "operator@example.com", "a-secure-password", "Ops")
        operator = portal.authenticate(self.connection, "operator@example.com", "a-secure-password")
        self.assertEqual(created["role"], "operator")
        self.assertEqual(operator.role, "operator")
        token, csrf = portal.create_session(self.connection, operator.id)
        self.assertEqual(portal.public_user(*portal.user_for_session(self.connection, token))["role"], "operator")
        self.assertTrue(csrf)

    def test_password_reset_is_one_time_and_revokes_sessions(self):
        user = self.approved_user()
        session, _ = portal.create_session(self.connection, user.id)
        portal.request_password_reset(self.connection, user.email, "https://stock.example")
        body = self.connection.execute(
            "SELECT text_body FROM email_outbox WHERE subject LIKE 'Reset your%' ORDER BY id DESC"
        ).fetchone()[0]
        reset_url = next(part for part in body.split() if part.startswith("https://"))
        token = parse_qs(urlparse(reset_url).query)["token"][0]
        portal.reset_password(self.connection, token, "a-new-secure-password")
        self.assertIsNone(portal.user_for_session(self.connection, session))
        self.assertIsNotNone(portal.authenticate(self.connection, user.email, "a-new-secure-password"))
        with self.assertRaises(portal.PortalError):
            portal.reset_password(self.connection, token, "another-secure-password")

    def test_operator_holds_stock_and_confirms_offline_payment(self):
        user = self.approved_user()
        request = portal.create_request(self.connection, user, {
            "request_type": "stock", "product_id": 42, "quantity": 6, "destination": "London",
        }, {"id": 42, "brand": "Example", "sku": "SKU-42"})
        portal.issue_quote(self.connection, request["reference"], 120, "EUR", "2099-12-31")
        reservation = portal.hold_stock(self.connection, request["reference"], 10)
        self.assertEqual(portal.reserved_quantity(self.connection, 42), 6)
        result = portal.confirm_reservation(self.connection, reservation["id"], "Bank transfer received")
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(self.connection.execute("SELECT status FROM reservations").fetchone()[0], "confirmed")

    def test_expired_hold_cannot_be_confirmed(self):
        user = self.approved_user()
        request = portal.create_request(self.connection, user, {
            "request_type": "stock", "product_id": 42, "quantity": 1, "destination": "London",
        }, {"id": 42, "brand": "Example"})
        portal.issue_quote(self.connection, request["reference"], 20, "EUR", "2099-12-31")
        reservation = portal.hold_stock(self.connection, request["reference"], 10)
        self.connection.execute("UPDATE reservations SET expires_at='2000-01-01T00:00:00+00:00'")
        self.connection.commit()
        with self.assertRaises(portal.PortalError):
            portal.confirm_reservation(self.connection, reservation["id"])
        self.assertEqual(self.connection.execute("SELECT status FROM reservations").fetchone()[0], "expired")

    def test_reservations_prevent_overselling_between_organizations(self):
        first = self.approved_user()
        second = self.approved_user("second@example.com", "Second Co")
        requests = []
        for user in (first, second):
            request = portal.create_request(self.connection, user, {
                "request_type": "stock", "product_id": 9, "quantity": 6, "destination": "London",
            }, {"id": 9, "brand": "Example"})
            portal.issue_quote(self.connection, request["reference"], 60, "EUR", "2099-12-31")
            requests.append(request)
        portal.hold_stock(self.connection, requests[0]["reference"], 10)
        with self.assertRaises(portal.ConflictError):
            portal.hold_stock(self.connection, requests[1]["reference"], 10)

    def test_existing_database_is_migrated_without_losing_users(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "portal.db"
            connection = sqlite3.connect(database)
            connection.executescript("""
                CREATE TABLE organizations (id INTEGER PRIMARY KEY, name TEXT NOT NULL, country TEXT NOT NULL, registration_number TEXT, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
                CREATE TABLE users (id INTEGER PRIMARY KEY, organization_id INTEGER NOT NULL REFERENCES organizations(id), email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, display_name TEXT, status TEXT NOT NULL DEFAULT 'active', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_login_at TEXT);
                INSERT INTO organizations (name,country) VALUES ('Existing Co','GB');
                INSERT INTO users (organization_id,email,password_hash) VALUES (1,'existing@example.com','preserved');
            """)
            connection.close()
            portal.ensure_schema(database)
            migrated = portal.connect_portal(database, use_wal=False)
            try:
                self.assertIn("role", {row[1] for row in migrated.execute("PRAGMA table_info(users)")})
                self.assertEqual(migrated.execute("SELECT email FROM users").fetchone()[0], "existing@example.com")
                self.assertIsNotNone(migrated.execute("SELECT name FROM sqlite_master WHERE name='reservations'").fetchone())
            finally:
                migrated.close()


if __name__ == "__main__":
    unittest.main()
