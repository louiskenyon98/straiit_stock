from __future__ import annotations

import os
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.database import (
    CompatRow,
    media_base_url,
    postgres_sql,
    postgres_url,
    safe_database_label,
    using_postgres,
)


class DatabaseCompatibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime_directory = tempfile.TemporaryDirectory()
        self.runtime_patch = patch(
            "api.database.RUNTIME_CONFIG",
            Path(self.runtime_directory.name) / "missing-runtime.json",
        )
        self.runtime_patch.start()

    def tearDown(self) -> None:
        self.runtime_patch.stop()
        self.runtime_directory.cleanup()

    def test_environment_url_precedence(self) -> None:
        values = {
            "DATABASE_URL": "postgresql://app:secret@pooled.example.test/straiit",
            "NEON_DATABASE_URL": "postgresql://fallback@example.test/fallback",
            "NEON_DIRECT_DATABASE_URL": "postgresql://direct@example.test/direct",
        }
        with patch.dict(os.environ, values, clear=True):
            self.assertEqual(postgres_url(), values["DATABASE_URL"])

    def test_direct_migration_url_is_an_accepted_local_fallback(self) -> None:
        value = "postgresql://app:secret@direct.example.test/straiit"
        with patch.dict(os.environ, {"NEON_DIRECT_DATABASE_URL": value}, clear=True):
            self.assertEqual(postgres_url(), value)
            self.assertEqual(
                safe_database_label(),
                "PostgreSQL database straiit at direct.example.test",
            )
            self.assertNotIn("secret", safe_database_label())

    def test_url_can_come_from_ignored_runtime_config(self) -> None:
        value = "postgresql://app:secret@local-config.example.test/straiit"
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "runtime.local.json"
            config.write_text(
                json.dumps({"use_neon": True, "neon_database_url": value}),
                encoding="utf-8",
            )
            with patch.dict(os.environ, {}, clear=True), patch(
                "api.database.RUNTIME_CONFIG", config
            ):
                self.assertEqual(postgres_url(), value)
                self.assertTrue(using_postgres())

    def test_media_origin_can_come_from_runtime_config(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "runtime.local.json"
            config.write_text(
                json.dumps({
                    "use_neon": False,
                    "media_base_url": "https://bucket.s3.example.test/",
                }),
                encoding="utf-8",
            )
            with patch("api.database.RUNTIME_CONFIG", config):
                self.assertEqual(
                    media_base_url(), "https://bucket.s3.example.test"
                )

    def test_sqlite_placeholders_are_translated(self) -> None:
        self.assertEqual(
            postgres_sql("SELECT * FROM products WHERE id=? AND brand=?"),
            "SELECT * FROM products WHERE id=%s AND brand=%s",
        )

    def test_environment_can_override_the_local_toggle(self) -> None:
        with patch.dict(os.environ, {"STRAIIT_USE_NEON": "false"}, clear=True):
            self.assertFalse(using_postgres())
        with patch.dict(os.environ, {"STRAIIT_USE_NEON": "true"}, clear=True):
            self.assertTrue(using_postgres())

    def test_postgres_rows_support_mapping_and_numeric_access(self) -> None:
        row = CompatRow({"count": 12, "name": "Stock"})
        self.assertEqual(row[0], 12)
        self.assertEqual(row["name"], "Stock")


if __name__ == "__main__":
    unittest.main()
