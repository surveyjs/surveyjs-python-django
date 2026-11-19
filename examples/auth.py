"""May this user do it? The examples call these and nothing else, so this is where your real checks go.

request.user is Django's own user: in this demo, demo/users.py signs in Alice or Bob from a cookie; a real app uses
django.contrib.sessions with AuthenticationMiddleware (or a token), and these checks don't change.
"""

from typing import Any, Literal

from examples.models import File

Ability = Literal["edit-forms"]


def can(user: Any, ability: Ability) -> bool:
    """Saving definitions (creator-load-save, lint-definition) and variable presets is an editor action: the
    examples.edit_forms permission, which the seed grants to the Editors group. Your real check goes here:
    roles, teams, form ownership…"""
    if ability == "edit-forms":
        return user.has_perm("examples.edit_forms")
    raise ValueError(f"Unknown ability {ability}")


async def acan(user: Any, ability: Ability) -> bool:
    """can() for async views and the relays."""
    if ability == "edit-forms":
        return await user.ahas_perm("examples.edit_forms")
    raise ValueError(f"Unknown ability {ability}")


def can_read_file(user: Any, file: File | None) -> bool:
    """May this user read this uploaded file (store-files)? Any signed-in user may here; real apps check
    ownership, for example file.owner_id == user.id. A denial answers 404, so it doesn't confirm the file exists."""
    return user.is_authenticated and file is not None
