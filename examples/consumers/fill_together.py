"""Fill Forms Together: the relay behind CollaborationPlugin from survey-core/collaboration, a Channels consumer at
/ws/rooms/<record_id> (examples/routing.py). Wire protocol: https://github.com/surveyjs/collaborative-form-filling
(PROTOCOL.md). The rooms are in examples/relay/fill_room.py. The relay saves the finished job sheet itself, once
per room session.
"""

import json
import logging
import re
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from examples.integration.stored_json import dumps, insert_response
from examples.models import Form, Response
from examples.relay import fill_room, room_key
from examples.relay.messages import display_name, parse

log = logging.getLogger("examples.relay")

RECORD_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")   # the ids the reference relay accepts


def seed(record_id: str) -> tuple[Any, dict[str, Any]]:
    """The job sheet definition, and the saved answers when the record exists (otherwise a blank sheet)."""
    form = Form.objects.filter(key="job-sheet").first()
    saved = Response.objects.filter(form_id="job-sheet", id=record_id).first() if record_id.isdigit() else None
    values = json.loads(saved.data) if saved else {}
    return json.loads(form.json) if form else {}, values if isinstance(values, dict) else {}


class FillTogetherConsumer(AsyncWebsocketConsumer):
    room: fill_room.FillRoom
    participant: fill_room.Participant

    # region sjs:fill-together.server
    # The relay runs in this app's process, on its port, and relays JSON: it never parses the definition
    async def connect(self):
        record_id, user = self.scope["url_route"]["kwargs"]["record_id"], self.scope["user"]
        key = room_key.for_scope(self.scope, record_id)
        if not user.is_authenticated or not RECORD_ID.match(record_id) or key is None:   # stands in for your session check
            await self.close()   # before accept(): the browser sees a refused handshake
            return
        await self.accept()
        self.room = await fill_room.join(key, lambda: database_sync_to_async(seed)(record_id))   # definition + answers
        self.participant = self.room.add(display_name(self.scope, user.get_full_name()))
        await self.channel_layer.group_add(self.room.group, self.channel_name)
        await self.send(text_data=dumps({
            "type": "init", "clientId": self.participant.id, "name": self.participant.name,
            "colorIndex": self.room.color_index(self.participant), "seed": self.room.seed, "values": self.room.values,
            "peers": self.room.roster(self.participant), "sessionId": self.room.session_id,
            "responseId": self.room.response_id,
        }))   # init first

    async def receive(self, text_data=None, bytes_data=None):
        message = parse(text_data)   # objects stay objects: {} is relayed as {}
        if not isinstance(message, dict):
            return
        kind = message.get("type")
        if kind == "complete" and isinstance(message.get("data"), dict):
            await self.complete(message["data"])
        elif kind == "value" and isinstance(message.get("key"), str) and self.room.response_id is None:
            self.room.values[message["key"]] = message.get("value")   # last write wins
            await self.broadcast({"type": "value", "from": self.participant.id, "key": message["key"],
                                  "value": message.get("value")})
        elif kind == "presence" and message.get("state") is not None and len(text_data) <= 4096:
            retain = message.get("retain") is not False   # stamp identity, relay
            if retain:
                self.participant.state = message["state"]
            await self.broadcast({"type": "peer", "retain": retain, "peer": self.room.peer(self.participant, message["state"])})
        # unknown types: ignore

    async def disconnect(self, code):
        if hasattr(self, "participant"):   # peer-left to the others; the room is dropped 2 s after the last leaves
            fill_room.leave(self.room, self.participant)
            await self.broadcast({"type": "peer-left", "clientId": self.participant.id})
            await self.channel_layer.group_discard(self.room.group, self.channel_name)
    # endregion

    # region sjs:fill-together.complete
    # Save once per room session and send the same confirmation to every participant
    async def complete(self, data: dict[str, Any]) -> None:
        async with self.room.lock:   # two completes at once: the second waits, then finds the saved id
            if self.room.response_id is None:
                try:
                    self.room.response_id = await database_sync_to_async(insert_response)("job-sheet", data)   # as save-response does
                except Exception:
                    log.exception("fill-together: couldn't save the job sheet")
                    await self.send(text_data=dumps({"type": "save-error", "error": "Couldn't save the job sheet. Please try again."}))
                    return
                self.room.values = dict(data)
        await self.broadcast({"type": "completed", "id": self.room.response_id, "data": self.room.values}, everyone=True)
    # endregion

    async def broadcast(self, message: dict[str, Any], everyone: bool = False) -> None:
        """Send to the room through the channel layer: to everyone else (nobody gets their own echo), or everyone."""
        await self.channel_layer.group_send(self.room.group, {
            "type": "relay.message", "text": dumps(message), "sender": None if everyone else self.participant.id})
        if message["type"] != "peer":
            self.room.changed()

    async def relay_message(self, event: dict[str, Any]) -> None:
        """A broadcast from the room's group. Channels runs a consumer's handlers one at a time, so a socket never
        gets two sends at once."""
        if event["sender"] != self.participant.id:
            await self.send(text_data=event["text"])
