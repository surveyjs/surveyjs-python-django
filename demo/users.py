"""Demo only: a demo_user cookie picks Alice (premium, editor), Bob (basic, viewer) or Signed out ("none").

DemoUserMiddleware stands in for django.contrib.auth's AuthenticationMiddleware: it sets request.user (lazily) and
request.auser to the User whose username is the cookie, or AnonymousUser. A real app uses django.contrib.sessions
with AuthenticationMiddleware, and the views don't change: they read request.user and call examples/auth.py.
DemoUserWebSocketMiddleware does the same for the relays, which Django's middleware never sees.

Pages that show user context or authorization offer a switch (PAGES). Every other page signs in as Alice, so a
choice made on one page never breaks another.
"""

from collections.abc import Mapping

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from django.http import HttpRequest, HttpResponseBase
from django.http.cookie import parse_cookie
from django.utils.functional import SimpleLazyObject

from examples.middleware import SyncAndAsyncMiddleware
from examples.models import User

USERS = ("alice", "bob")

LABELS = {"alice": "Alice (premium, editor)", "bob": "Bob (basic, viewer)", "none": "Signed out"}

PAGES: dict[str, list[str]] = {
    "load-definition-variables-data": ["alice", "bob"],   # compare premium and basic customer variables
    "resume-progress": ["alice", "bob"],                  # keep an independent draft for each respondent
    "creator-load-save": ["alice", "bob"],                # Bob's saves answer 403 (can(user, "edit-forms"))
}
"""Example slug => the users its switch offers. The first is the default."""

_YEAR = 365 * 24 * 3600


def for_page(slug: str) -> list[str]:
    """The users an example page offers; one means no switch."""
    return PAGES.get(slug, ["alice"])


def page_user(slug: str, cookies: Mapping[str, str]) -> str:
    """The cookie's user if the page offers it, otherwise the page's default."""
    users = for_page(slug)
    cookie = cookies.get("demo_user")
    return cookie if cookie in users else users[0]


def demo_user_key(path: str, cookies: Mapping[str, str]) -> str | None:
    """The demo user a request runs as. /claim is Option A of load-definition-variables-data: it renders that
    example's page, so it signs in the same way. On the API an absent, unknown or "none" cookie is signed out."""
    if path == "/claim":
        return page_user("load-definition-variables-data", cookies)
    key = cookies.get("demo_user")
    return key if key in USERS else None


def find_user(key: str | None) -> User | AnonymousUser:
    return (User.objects.filter(username=key).first() if key else None) or AnonymousUser()


async def afind_user(key: str | None) -> User | AnonymousUser:
    return (await User.objects.filter(username=key).afirst() if key else None) or AnonymousUser()


def _sign_in(request: HttpRequest, key: str | None) -> None:
    request.user = SimpleLazyObject(lambda: find_user(key))

    async def auser() -> User | AnonymousUser:
        return await afind_user(key)
    request.auser = auser


class DemoUserMiddleware(SyncAndAsyncMiddleware):
    """request.user from the demo_user cookie, looked up when a view first asks."""

    def process_request(self, request: HttpRequest) -> None:
        _sign_in(request, demo_user_key(request.path, request.COOKIES))


class DemoUserWebSocketMiddleware(BaseMiddleware):
    """scope["user"] for the relays, from the same cookie (Channels' AuthMiddlewareStack in a real app)."""

    async def __call__(self, scope, receive, send):
        header = next((value for name, value in scope.get("headers", []) if name == b"cookie"), b"")
        key = demo_user_key(scope["path"], parse_cookie(header.decode("latin-1")))
        user = await database_sync_to_async(find_user)(key)   # closes its connection: the sandbox stays deletable
        return await super().__call__({**scope, "user": user}, receive, send)


def sign_in_for_page(slug: str, request: HttpRequest, response: HttpResponseBase) -> None:
    """On an example page: keep the cookie's user if the page offers it, otherwise sign in as the page's default
    and set demo_user to it. host.js writes the cookie back on each tab's focus, so it isn't httponly."""
    key = page_user(slug, request.COOKIES)
    _sign_in(request, key)
    if request.COOKIES.get("demo_user") != key:
        response.set_cookie("demo_user", key, max_age=_YEAR, path="/", samesite="Lax", httponly=False,
                            secure=request.is_secure())
