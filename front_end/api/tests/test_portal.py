import sqlite3
import unittest

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


if __name__ == "__main__":
    unittest.main()
