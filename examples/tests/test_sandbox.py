"""The visitor sandbox (DEMO_MODE): a private copy of the seeded database per demo_sid, made with sqlite3's backup;
rows written by sync and async views land in it and not in the app's database; an invite link adopts a sandbox;
and the pruner removes sandboxes unused for 24 hours, on Windows too."""

import io
import json
import os
import re
import time
from pathlib import Path

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from demo.sandbox import prune
from examples.models import Response
from examples.tests.helpers import MockService, SandboxTestCase, answer, asgi_client, drop_sandbox_aliases, switched


def sandbox_file(sid: str) -> Path:
    return Path(settings.DATA_DIR) / "sandbox" / f"{sid}.sqlite"


@override_settings(DEMO_MODE=True)
class SandboxTests(SandboxTestCase):
    def test_each_visitor_gets_a_copy_and_writes_land_in_it(self) -> None:
        async def run() -> dict:
            async with asgi_client(cookies={"demo_user": "alice"}) as mine, asgi_client(cookies={"demo_user": "alice"}) as theirs:
                first = await mine.get("/demo/stored/save-response")
                saved = (await mine.post("/api/responses", json={"formId": "contact", "data": {"mine": True}})).json()["id"]
                await theirs.get("/demo/stored/save-response")
                return {"set_cookie": first.headers.get("set-cookie", ""), "mine": mine.cookies.get("demo_sid"),
                        "theirs": theirs.cookies.get("demo_sid"), "saved": saved,
                        "mine_sees": (await mine.get(f"/demo/stored/save-response?id={saved}")).json(),
                        "theirs_sees": (await theirs.get(f"/demo/stored/save-response?id={saved}")).json()}
        result = async_to_sync(run)()
        self.assertTrue(re.fullmatch(r"[0-9a-f]{32}", result["mine"]))
        self.assertNotEqual(result["mine"], result["theirs"])
        self.assertIn("HttpOnly", result["set_cookie"])
        self.assertIn("SameSite=Lax", result["set_cookie"])
        self.assertTrue(sandbox_file(result["mine"]).is_file() and sandbox_file(result["theirs"]).is_file())
        self.assertEqual([row["data"] for row in result["mine_sees"]["responses"]], [{"mine": True}])
        self.assertFalse(any(row["data"] == {"mine": True} for row in result["theirs_sees"]["responses"]))
        self.assertFalse(Response.objects.filter(data='{"mine":true}').exists())   # not in the app's database

    def test_async_views_write_to_the_sandbox_too(self) -> None:
        async def run() -> list:
            with switched(VALIDATE_RESPONSES=True, DEMO_MODE=True), MockService(answer(200, {})):
                async with asgi_client(cookies={"demo_user": "alice"}) as client:
                    r = await client.post("/api/responses", json={"formId": "claim", "data": {"async": True}})
                    seen = (await client.get(f"/demo/stored/validate-response?id={r.json()['id']}")).json()
                    return [r.status_code, seen["responses"], client.cookies.get("demo_sid")]
        status, rows, sid = async_to_sync(run)()
        self.assertEqual(status, 201)
        self.assertEqual([row["data"] for row in rows], [{"async": True}])
        self.assertFalse(Response.objects.filter(data='{"async":true}').exists())
        self.assertTrue(sandbox_file(sid).is_file())

    def test_an_invite_link_adopts_the_sandbox_and_an_unknown_one_says_it_expired(self) -> None:
        async def run() -> dict:
            async with asgi_client(cookies={"demo_user": "alice"}) as host, asgi_client(cookies={"demo_user": "alice"}) as guest:
                await host.get("/demo/stored/fill-together")
                sid = host.cookies.get("demo_sid")
                joined = await guest.get(f"/examples/fill-together?join={sid}")
                expired = await guest.get(f"/examples/fill-together?join={'0' * 32}")
                return {"sid": sid, "guest": guest.cookies.get("demo_sid"), "joined": joined.text, "expired": expired.text}
        result = async_to_sync(run)()
        self.assertNotIn("invite link has expired", result["joined"])
        self.assertIn("That invite link has expired, so you have a fresh copy of the demo data.", result["expired"])
        self.assertNotEqual(result["guest"], result["sid"])   # the expired invite gave a fresh sandbox
        self.assertIn(f'"sandboxId": "{result["sid"]}"', result["joined"])

    def test_up_and_static_files_need_no_sandbox(self) -> None:
        async def run() -> list:
            async with asgi_client() as client:
                return [(await client.get(path)).headers.get("set-cookie") for path in ("/up", "/shared/ui/page-tabs.js")]
        self.assertEqual(async_to_sync(run)(), [None, None])

    def test_the_pruner_removes_sandboxes_unused_for_a_day(self) -> None:
        async def make() -> str:
            async with asgi_client(cookies={"demo_user": "alice"}) as client:
                await client.post("/api/responses", json={"formId": "contact", "data": {}})
                return client.cookies.get("demo_sid")
        sid = async_to_sync(make)()
        drop_sandbox_aliases()   # every connection is closed: CONN_MAX_AGE 0, and the test's own here
        database = sandbox_file(sid)
        self.assertEqual(prune(), 0)   # used just now
        day_ago = time.time() - 25 * 3600
        os.utime(database, (day_ago, day_ago))
        call_command("prune_sandboxes", stdout=io.StringIO())
        self.assertFalse(database.exists())
        self.assertFalse((database.parent / sid).exists())
        self.assertFalse(any(database.parent.glob(f"{sid}.sqlite*")))

    def test_outside_demo_mode_nothing_is_sandboxed(self) -> None:
        async def run() -> str | None:
            with override_settings(DEMO_MODE=False):
                async with asgi_client() as client:
                    return (await client.get("/demo/stored/save-response")).headers.get("set-cookie")
        before = set((Path(settings.DATA_DIR) / "sandbox").glob("*.sqlite"))
        self.assertIsNone(async_to_sync(run)())
        self.assertEqual(set((Path(settings.DATA_DIR) / "sandbox").glob("*.sqlite")), before)
