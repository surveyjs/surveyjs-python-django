#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

# Before anything imports Django: this project needs Python 3.14 or newer
if sys.version_info < (3, 14):
    print(f"Python 3.14 or newer is required (this is {sys.version.split()[0]})", file=sys.stderr)
    raise SystemExit(1)


def main():
    """Run administrative tasks."""
    # `manage.py test` runs with config/settings_test.py: a temporary DATA_DIR, and every private key and switch
    # off, so a developer's .env never changes a test result
    default = 'config.settings_test' if sys.argv[1:2] == ['test'] else 'config.settings'
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', default)
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
