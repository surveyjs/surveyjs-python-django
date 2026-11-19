"""The relays, driven through config.asgi.application with asgiref's ApplicationCommunicator: init first with every
field, values and records reach the others, complete saves once for everyone, presence-sync, 500 appends in
order, the connections each relay refuses, and separate rooms per sandbox in demo mode."""

import asyncio
import json
import uuid

from asgiref.sync import async_to_sync
from django.test import TransactionTestCase, override_settings

from examples.models import Response
from examples.relay.room_key import room_key, snapshot_path
from examples.tests.helpers import SandboxTestCase, Socket, asgi_client


def room() -> str:
    """A fresh room id per test: rooms outlive a test by 2 s, in the process."""
    return f"test-{uuid.uuid4().hex[:12]}"


class RelayTests(TransactionTestCase):
    def run_async(self, coroutine) -> None:
        async_to_sync(lambda: coroutine)()

    def test_fill_init_has_every_field_and_values_reach_the_others(self) -> None:
        async def run() -> None:
            id = room()
            ann = Socket(f"/ws/rooms/{id}?name=Ann")
            self.assertTrue(await ann.connect())
            init = await ann.receive()
            self.assertEqual(init["type"], "init")
            self.assertEqual(set(init), {"type", "clientId", "name", "colorIndex", "seed", "values", "peers", "sessionId", "responseId"})
            self.assertEqual((init["name"], init["colorIndex"], init["responseId"], len(init["sessionId"])), ("Ann", 1, None, 32))
            self.assertTrue(init["seed"]["title"])
            ben = Socket(f"/ws/rooms/{id}?name=Ben")
            self.assertTrue(await ben.connect())
            self.assertEqual((await ben.receive())["sessionId"], init["sessionId"])
            await ann.send({"type": "value", "key": "q1", "value": {"d": {}, "g": 1.0}})
            self.assertEqual(await ben.next_of("value"), {"type": "value", "from": init["clientId"], "key": "q1", "value": {"d": {}, "g": 1.0}})
            await ann.send({"type": "presence", "state": {"focus": "q1"}, "retain": True})
            peer = await ben.next_of("peer")
            self.assertEqual((peer["retain"], peer["peer"]["clientId"]), (True, init["clientId"]))
            await ann.send_text("not json")
            await ann.send({"type": "nonsense"})
            cat = Socket(f"/ws/rooms/{id}?name=Cat")
            self.assertTrue(await cat.connect())
            late = await cat.receive()
            self.assertEqual(late["values"]["q1"], {"d": {}, "g": 1.0})
            self.assertEqual([p["clientId"] for p in late["peers"]], [init["clientId"]])
            await cat.close()
            await ben.close()
            self.assertTrue((await ann.next_of("peer-left"))["clientId"])
            await ann.close()
        async_to_sync(run)()

    def test_fill_two_completes_save_one_row_for_everyone(self) -> None:
        before = Response.objects.filter(form_id="job-sheet").count()

        async def run() -> None:
            id = room()
            ann, ben = Socket(f"/ws/rooms/{id}?name=Ann"), Socket(f"/ws/rooms/{id}?name=Ben")
            for socket in (ann, ben):
                self.assertTrue(await socket.connect())
                await socket.receive()
            data = {"q1": "done", "d": {}, "g": 1.5}
            await ann.send({"type": "complete", "data": data})
            await ben.send({"type": "complete", "data": data})
            first, second = await ann.next_of("completed"), await ann.next_of("completed")
            self.assertEqual((first["id"], first["data"]), (second["id"], data))
            self.assertEqual((await ben.next_of("completed"))["id"], first["id"])
            await ann.send({"type": "value", "key": "q1", "value": "changed after completing"})
            cat = Socket(f"/ws/rooms/{id}?name=Cat")
            self.assertTrue(await cat.connect())
            late = await cat.receive()
            self.assertEqual((late["responseId"], late["values"]["q1"]), (first["id"], "done"))
            for socket in (cat, ben, ann):
                await socket.close()
        async_to_sync(run)()
        self.assertEqual(Response.objects.filter(form_id="job-sheet").count(), before + 1)

    def test_fill_seeds_a_room_from_the_saved_record(self) -> None:
        saved = Response.objects.filter(form_id="job-sheet").order_by("id").first()

        async def run() -> dict:
            socket = Socket(f"/ws/rooms/{saved.id}")
            self.assertTrue(await socket.connect())
            init = await socket.receive()
            await socket.close()
            return init
        init = async_to_sync(run)()
        self.assertEqual((init["values"], init["name"]), (json.loads(saved.data), "Alice Martin"))

    def test_edit_records_reach_late_joiners_in_order_and_presence_sync_follows_init(self) -> None:
        async def run() -> None:
            id = room()
            records = [{"seq": 1, "op": 0, "payload": {"name": "title", "value": "One"}}, {"seq": 1, "op": 0, "payload": {}}]
            ann = Socket(f"/ws/forms/{id}?name=Ann")
            self.assertTrue(await ann.connect())
            init = await ann.receive()
            self.assertEqual(set(init), {"type", "clientId", "colorIndex", "color", "seed", "log"})
            self.assertEqual(init["log"], [])
            await ann.send({"type": "presence", "state": {"tab": "designer"}})
            ben = Socket(f"/ws/forms/{id}?name=Ben")
            self.assertTrue(await ben.connect())
            self.assertEqual((await ben.receive())["type"], "init")
            sync = await ben.receive()
            self.assertEqual((sync["type"], sync["peers"][0]["clientId"]), ("presence-sync", init["clientId"]))
            for record in records:
                await ann.send({"type": "append", "payload": record})
            self.assertEqual([(await ben.next_of("record"))["payload"] for _ in records], records)
            cat = Socket(f"/ws/forms/{id}?name=Cat")
            self.assertTrue(await cat.connect())
            self.assertEqual((await cat.receive())["log"], records)
            await cat.close()
            await ben.close()
            self.assertTrue((await ann.next_of("presence-leave"))["clientId"])
            await ann.close()
        async_to_sync(run)()

    def test_five_hundred_appends_arrive_in_order(self) -> None:
        async def run() -> None:
            id = room()
            ann, ben = Socket(f"/ws/forms/{id}?name=Ann"), Socket(f"/ws/forms/{id}?name=Ben")
            for socket in (ann, ben):
                self.assertTrue(await socket.connect())
                await socket.receive()
            await asyncio.gather(*(ann.send({"type": "append", "payload": {"n": n}}) for n in range(500)))
            received = [(await ben.next_of("record"))["payload"]["n"] for _ in range(500)]
            self.assertEqual(received, list(range(500)))
            await ben.close()
            await ann.close()
        async_to_sync(run)()

    def test_refused_connections_close_before_accept(self) -> None:
        async def run() -> None:
            for path, user in (("/ws/rooms/x", None), ("/ws/rooms/x", "mallory"), ("/ws/forms/x", None),
                               ("/ws/forms/x", "bob"), ("/ws/rooms/bad%20id", "alice"), ("/ws/forms/" + "x" * 65, "alice")):
                self.assertFalse(await Socket(path, user=user).connect(), f"{path} as {user}")
        async_to_sync(run)()


@override_settings(DEMO_MODE=True)
class SandboxRoomTests(SandboxTestCase):
    def test_sandboxes_get_their_own_rooms_and_snapshots(self) -> None:
        async def run() -> None:
            async with asgi_client(cookies={"demo_user": "alice"}) as mine, asgi_client(cookies={"demo_user": "alice"}) as theirs:
                await mine.get("/demo/stored/fill-together")
                await theirs.get("/demo/stored/fill-together")
                my_sid, their_sid = mine.cookies.get("demo_sid"), theirs.cookies.get("demo_sid")
                self.assertNotEqual(my_sid, their_sid)
                self.assertFalse(await Socket("/ws/rooms/shared").connect())   # no demo_sid, no sandbox: refused
                first = Socket("/ws/rooms/shared", sid=my_sid)
                self.assertTrue(await first.connect())
                await first.receive()
                await first.send({"type": "value", "key": "q1", "value": "mine"})
                same = Socket("/ws/rooms/shared", sid=my_sid)
                self.assertTrue(await same.connect())
                self.assertEqual((await same.receive())["values"].get("q1"), "mine")
                other = Socket("/ws/rooms/shared", sid=their_sid)
                self.assertTrue(await other.connect())
                self.assertNotIn("q1", (await other.receive())["values"])
                snapshot = snapshot_path(room_key(my_sid, "shared"))
                self.assertTrue(snapshot.is_file())
                self.assertNotIn(":", snapshot.name)
                stored = (await mine.get("/demo/stored/fill-together?room=shared")).json()
                self.assertEqual(stored["relay room"]["values"], {"q1": "mine"})
                for socket in (other, same, first):
                    await socket.close()
        async_to_sync(run)()
