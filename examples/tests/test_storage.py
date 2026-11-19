"""Storage through the ORM: the models keep the docs' table and column names, documents are text, a field inside a
document is filtered with json_extract, the database runs in WAL mode, and two concurrent upserts of one key
serialize instead of failing."""

import json
import threading

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.test.client import Client

from examples.db import JsonExtract
from examples.models import Claim, Customer, File, Form, Office, Progress, Response, ShippingRate, User, VariablePreset

TABLES = {
    "users": None, "forms": ["key", "json"], "responses": ["id", "form_id", "definition_version", "data", "created_at"],
    "progress": ["key", "json"], "files": ["id", "name", "type"], "offices": ["id", "name", "region"],
    "customers": ["email"], "shipping_rates": ["postcode_prefix", "price"],
    "claims": ["id", "customer_email", "amount", "response_id"], "variable_presets": ["key", "json"],
}
MODELS = [User, Form, Response, Progress, File, Office, Customer, ShippingRate, Claim, VariablePreset]


class StorageTests(TestCase):
    def test_models_use_the_docs_tables_and_columns(self) -> None:
        self.assertEqual([model._meta.db_table for model in MODELS], list(TABLES))
        with connection.cursor() as cursor:
            for table, columns in TABLES.items():
                found = [column.name for column in connection.introspection.get_table_description(cursor, table)]
                if columns is not None:
                    self.assertEqual(sorted(found), sorted(columns), table)
        self.assertIn("plan", [field.column for field in User._meta.fields])

    def test_created_at_is_iso_8601_utc_text(self) -> None:
        id = self.client.post("/api/responses", json.dumps({"formId": "storage", "data": {}}), content_type="application/json").json()["id"]
        self.assertRegex(Response.objects.get(id=id).created_at, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_json_extract_filters_inside_a_document(self) -> None:
        emails = Response.objects.annotate(email=JsonExtract("data", "$.customer_email")).filter(
            form_id="claim", email="alice@example.com")
        self.assertTrue(emails.exists())
        self.assertTrue(all(json.loads(row.data)["customer_email"] == "alice@example.com" for row in emails))

    def test_the_database_is_in_wal_mode(self) -> None:
        with connection.cursor() as cursor:
            cursor.execute("PRAGMA journal_mode")
            self.assertEqual(cursor.fetchone()[0], "wal")


class ConcurrentUpsertTests(TransactionTestCase):
    def test_two_puts_of_one_key_at_once_both_succeed(self) -> None:
        statuses: list[int] = []
        barrier = threading.Barrier(2)

        def put(title: str) -> None:
            client = Client()
            client.cookies["demo_user"] = "alice"
            barrier.wait()
            statuses.append(client.put("/api/forms/concurrent", json.dumps({"title": title}), content_type="application/json").status_code)
            connection.close()

        threads = [threading.Thread(target=put, args=(title,)) for title in ("one", "two")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(statuses, [204, 204])
        self.assertIn(json.loads(Form.objects.get(key="concurrent").json)["title"], ("one", "two"))
