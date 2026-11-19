from django.apps import AppConfig
from django.db.models.signals import post_migrate


class ExamplesConfig(AppConfig):
    name = 'examples'

    def ready(self):
        # After `migrate`: the idempotent seed (examples/seed.py). Nothing else here: `manage.py serve` checks its
        # port before anything touches the database or the data folder.
        from examples.seed import seed_after_migrate

        post_migrate.connect(seed_after_migrate, sender=self, dispatch_uid='examples.seed')
