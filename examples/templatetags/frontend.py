"""Demo only: {% import_map %}, the page's <script type="importmap"> (examples/frontend.py).

json_script can't write it: it always writes type="application/json". The map is built from constants, and
escaped as json_script escapes, so no value can end the script early.
"""

import json

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from examples import frontend

register = template.Library()

_ESCAPES = {ord(">"): "\\u003E", ord("<"): "\\u003C", ord("&"): "\\u0026"}   # as django.utils.html.json_script


@register.simple_tag
def import_map() -> str:
    escaped = json.dumps(frontend.import_map()).translate(_ESCAPES)
    return format_html('<script type="importmap">{}</script>', mark_safe(escaped))   # constants, escaped above
