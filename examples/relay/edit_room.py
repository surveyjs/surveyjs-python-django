"""Edit Forms Together rooms: the saved definition a room started from, every Creator record since (in arrival
order) and the people in it. examples/consumers/edit_together.py runs the relay; this file holds the rooms of this
process, by room key. Broadcasts go through the room's channel-layer group."""

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from django.conf import settings

from examples.relay.fill_room import Participant
from examples.relay.room_key import group_name, snapshot_path, write_snapshot

SLOTS = [1, 2, 3, 4, 6, 7, 8, 9]
"""Colour slots, skipping 5 (yellow is unreadable with white text); 0 is gray and never assigned."""

PALETTE = ["#808080", "#1570EF", "#CA4FFB", "#19B35C", "#19B394", "#F9C50B", "#F99130", "#F1529C", "#02ADEB", "#4E6198"]
"""The colour of each slot: the same values as survey-core's --sjs2-color-utility-user-bg-color-N."""


class EditRoom:
    def __init__(self, key: str, seed: Any) -> None:
        self.key = key
        self.group = group_name("edit", key)
        self.seed = seed
        self.log: list[Any] = []        # append-only: never deduplicated, replayed in this order
        self.participants: dict[str, Participant] = {}
        self.lock = asyncio.Lock()      # a join and an append never interleave: nobody gets a record twice or never
        self.drop_timer: asyncio.TimerHandle | None = None
        self._snapshot = snapshot_path(key, "edit") if settings.DEMO_MODE else None

    def add(self, name: str) -> Participant:
        taken = {p.slot for p in self.participants.values()}
        slot = next((slot for slot in SLOTS if slot not in taken), SLOTS[len(self.participants) % len(SLOTS)])
        participant = Participant(secrets.token_hex(8), name, slot)
        self.participants[participant.id] = participant
        self.changed()
        return participant

    @staticmethod
    def color(participant: Participant) -> str:
        return PALETTE[participant.slot]

    def peer(self, participant: Participant) -> dict[str, Any]:
        """Creator's plugin paints rings and cursors from `color`, so each peer carries it next to colorIndex."""
        return {"clientId": participant.id, "name": participant.name, "colorIndex": participant.slot,
                "color": self.color(participant), "state": participant.state}

    def roster(self, other_than: Participant) -> list[dict[str, Any]]:
        """Everyone else who has shared their presence."""
        return [self.peer(p) for p in self.participants.values() if p is not other_than and p.state is not None]

    def changed(self) -> None:
        """Demo only: the room's state for the Data panel (DEMO_MODE=true)."""
        if self._snapshot is not None:
            title = self.seed.get("title") if isinstance(self.seed, dict) else None
            write_snapshot(self._snapshot, {"participants": len(self.participants), "seed title": title,
                                            "records in the log": len(self.log)})


_rooms: dict[str, EditRoom] = {}


async def join(key: str, seed: Callable[[], Awaitable[Any]]) -> EditRoom:
    """The open room, or a new one seeded with the saved definition."""
    room = _rooms.get(key)
    if room is None:
        definition = await seed()
        room = _rooms.setdefault(key, EditRoom(key, definition))   # another join may have opened it meanwhile
    if room.drop_timer is not None:   # back within 2 s: keep the room
        room.drop_timer.cancel()
        room.drop_timer = None
    return room


def leave(room: EditRoom, participant: Participant) -> None:
    """The log lives until the room empties, and 2 s more."""
    room.participants.pop(participant.id, None)
    room.changed()
    if not room.participants:
        room.drop_timer = asyncio.get_running_loop().call_later(2, _drop_if_empty, room)


def _drop_if_empty(room: EditRoom) -> None:
    if not room.participants and _rooms.get(room.key) is room:
        del _rooms[room.key]
