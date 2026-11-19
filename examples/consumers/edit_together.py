"""Edit Forms Together: the relay behind CollaborationPlugin from survey-creator-core/collaboration, a Channels
consumer at /ws/forms/<form_id> (examples/routing.py). Wire protocol:
https://github.com/surveyjs/collaborative-form-editing (PROTOCOL.md). The rooms are in examples/relay/edit_room.py.
Saving is unchanged: Creator's Save button calls PUT /api/forms/<id> (creator-load-save).
"""

import json
import re
from typing import Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer

from examples.auth import acan
from examples.integration.stored_json import dumps
from examples.models import Form
from examples.relay import edit_room, room_key
from examples.relay.fill_room import Participant
from examples.relay.messages import display_name, parse

FORM_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def saved_definition(form_id: str) -> Any:
    """The definition saved through creator-load-save, or an empty one for a new form."""
    form = Form.objects.filter(key=form_id).first()
    return json.loads(form.json) if form else {}


class EditTogetherConsumer(AsyncWebsocketConsumer):
    room: edit_room.EditRoom
    participant: Participant

    # region sjs:edit-together.server
    # The same kind of relay as Fill Forms Together, keeping an append-only log instead of a value map:
    # Creator records must be replayed in order. It runs in this app's process, on its port.
    async def connect(self):
        form_id, user = self.scope["url_route"]["kwargs"]["form_id"], self.scope["user"]
        key = room_key.for_scope(self.scope, form_id)
        if not await acan(user, "edit-forms") or not FORM_ID.match(form_id) or key is None:   # like saving, editing together is for editors
            await self.close()   # before accept(): the browser sees a refused handshake
            return
        await self.accept()
        self.room = await edit_room.join(key, lambda: database_sync_to_async(saved_definition)(form_id))   # seed = the saved definition
        async with self.room.lock:   # the log in init, then every record after it: none twice, none missed
            self.participant = self.room.add(display_name(self.scope, user.get_full_name()))
            await self.channel_layer.group_add(self.room.group, self.channel_name)
            await self.send(text_data=dumps({"type": "init", "clientId": self.participant.id, "colorIndex": self.participant.slot,
                                             "color": self.room.color(self.participant), "seed": self.room.seed,
                                             "log": self.room.log}))   # init first
            if peers := self.room.roster(self.participant):
                await self.send(text_data=dumps({"type": "presence-sync", "peers": peers}))

    async def receive(self, text_data=None, bytes_data=None):
        message = parse(text_data)   # records stay opaque: {} is relayed as {}
        if not isinstance(message, dict):
            return
        if message.get("type") == "append" and message.get("payload") is not None:   # append, then fan out
            async with self.room.lock:
                self.room.log.append(message["payload"])
                await self.broadcast({"type": "record", "from": self.participant.id, "payload": message["payload"]})
        elif message.get("type") == "presence" and message.get("state") is not None and len(text_data) <= 4096:
            self.participant.state = message["state"]
            await self.broadcast({"type": "presence", "peer": self.room.peer(self.participant)})
        # unknown types: ignore

    async def disconnect(self, code):
        if hasattr(self, "participant"):   # presence-leave to the others; the log lives until the room empties
            edit_room.leave(self.room, self.participant)
            await self.broadcast({"type": "presence-leave", "clientId": self.participant.id})
            await self.channel_layer.group_discard(self.room.group, self.channel_name)
    # endregion

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send to everyone else in the room through the channel layer: nobody gets their own echo."""
        await self.channel_layer.group_send(self.room.group, {
            "type": "relay.message", "text": dumps(message), "sender": self.participant.id})
        if message["type"] != "presence":
            self.room.changed()

    async def relay_message(self, event: dict[str, Any]) -> None:
        """A broadcast from the room's group. Channels runs a consumer's handlers one at a time, so a socket never
        gets two sends at once."""
        if event["sender"] != self.participant.id:
            await self.send(text_data=event["text"])
