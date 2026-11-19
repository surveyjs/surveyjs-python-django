"""The tables the integration docs name, one model each, with the docs' table and column names (db_table, the
field names), so the SQL in the log or in `sqlite3` reads as the docs do.

A definition, a response, saved progress and a preset list are each one JSON document: a TextField holding the
text the app wrote (examples/integration/stored_json.py), never a JSONField, which decodes on read and encodes
again on save. created_at is ISO 8601 UTC text, so the dashboard's date filters are string comparisons.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """The demo users (Alice, Bob): Django's own user, plus the plan the forms read as {user.plan}."""

    plan = models.CharField(max_length=20, default='basic')

    class Meta:
        db_table = 'users'


class Form(models.Model):
    """A form definition, by key: what Creator saves and the pages load."""

    key = models.CharField(primary_key=True, max_length=255)
    json = models.TextField()

    class Meta:
        db_table = 'forms'
        # Editors may save definitions and variable presets: examples/auth.py checks it
        permissions = [('edit_forms', 'Can edit forms')]


class Response(models.Model):
    """A submitted response: its answers as one JSON document, and the definition version it was made with."""

    form_id = models.CharField(max_length=255, db_index=True)
    definition_version = models.CharField(max_length=255, null=True)
    data = models.TextField()
    created_at = models.CharField(max_length=20, db_index=True)

    class Meta:
        db_table = 'responses'


class Progress(models.Model):
    """A draft, keyed "<user id>:<formId>": { data, uiState } as the page sent it."""

    key = models.CharField(primary_key=True, max_length=255)
    json = models.TextField()

    class Meta:
        db_table = 'progress'


class File(models.Model):
    """An upload: the bytes are on disk, named by id, never by the client's file name."""

    id = models.CharField(primary_key=True, max_length=255)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255)

    class Meta:
        db_table = 'files'


class Office(models.Model):
    id = models.CharField(primary_key=True, max_length=255)
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255, db_index=True)

    class Meta:
        db_table = 'offices'


class Customer(models.Model):
    email = models.CharField(primary_key=True, max_length=255)

    class Meta:
        db_table = 'customers'


class ShippingRate(models.Model):
    postcode_prefix = models.CharField(primary_key=True, max_length=255)
    price = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        db_table = 'shipping_rates'


class Claim(models.Model):
    """The answers you query with SQL, copied from a claim response by their stable keys (valueName)."""

    response = models.ForeignKey(Response, on_delete=models.PROTECT, db_column='response_id', related_name='claims')
    customer_email = models.CharField(max_length=255, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)

    class Meta:
        db_table = 'claims'


class VariablePreset(models.Model):
    """The variable presets Creator's Preview tab offers for a form: one JSON document per form."""

    key = models.CharField(primary_key=True, max_length=255)
    json = models.TextField()

    class Meta:
        db_table = 'variable_presets'
