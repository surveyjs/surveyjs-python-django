"""Database plumbing the views share: SQLite's json_extract() as an ORM function, and where a request's data
lives (the app's database and uploads folder, or in demo mode a visitor's copy of both).

The only SQL written by hand in the examples is here, in the migrations and in demo/sandbox.py's copy.
"""

from contextvars import ContextVar
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db.models import Func, TextField, Value
from django.db.models.expressions import RawSQL
from django.http import HttpRequest


class JsonExtract(Func):
    """A field inside a stored JSON document: JsonExtract("data", "$.customer_email"), SQLite's json_extract().
    The document stays one TextField, and a filter on one of its fields stays an ORM query. On Postgres, use a
    JSONField copy of the column and KT("data__customer_email"), or ->>."""

    function = "json_extract"
    output_field = TextField()

    def __init__(self, field: str, path: str, **extra: Any) -> None:
        super().__init__(field, Value(path), **extra)


def rowid() -> RawSQL:
    """SQLite's rowid, the insertion order of a table whose primary key isn't a number (files: UUIDs)."""
    return RawSQL("rowid", ())


sandbox_database: ContextVar[str | None] = ContextVar("sandbox_database", default=None)
"""Demo only: the database alias of the visitor's sandbox, set by demo/sandbox.py for the request (None: the app's)."""


class SandboxRouter:
    """Demo only: sends every query to the visitor's sandbox while demo/sandbox.py has set one. Outside demo mode it
    returns None, and Django uses the default database. Sandboxes are copies of a migrated database, so migrate
    runs on the default one only."""

    def db_for_read(self, model: Any, **hints: Any) -> str | None:
        return sandbox_database.get()

    def db_for_write(self, model: Any, **hints: Any) -> str | None:
        return sandbox_database.get()

    def allow_migrate(self, db: str, app_label: str, **hints: Any) -> bool | None:
        return None if db == "default" else False


def uploads(request: HttpRequest) -> FileSystemStorage:
    """The folder the request's uploads live in, named by id (store-files): the visitor's in demo mode, which
    demo/sandbox.py puts into the ASGI scope, else <DATA_DIR>/files."""
    folder = getattr(request, "scope", {}).get("uploads") or Path(settings.DATA_DIR) / "files"
    return FileSystemStorage(location=folder)
