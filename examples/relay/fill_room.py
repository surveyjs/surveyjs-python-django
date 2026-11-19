"""Fill Forms Together rooms: the definition a room hands out, the latest value of every answer and the people in
it. examples/consumers/fill_together.py runs the relay; this file holds the rooms of this process, by room key.
Broadcasts go through the room's channel-layer group."""

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings

from examples.relay.room_key import group_name, snapshot_path, write_snapshot


@dataclass
class Participant:
    id: str
    name: str
    slot: int
    state: Any = None   # the last presence this participant shared (retained), or None


class FillRoom:
    def __init__(self, key: str, seed: Any, values: dict[str, Any]) -> None:
        self.key = key
        self.group = group_name("fill", key)
        self.seed = seed
        self.values = dict(values)               # question key => latest value; last write wins
        self.participants: dict[str, Participant] = {}
        self.response_id: int | None = None      # the response saved in this room session, once someone completes
        self.session_id = secrets.token_hex(16)  # 32 random hex characters per room instance
        self.lock = asyncio.Lock()               # one complete at a time: the room saves once
        self.drop_timer: asyncio.TimerHandle | None = None
        self._snapshot = snapshot_path(key) if settings.DEMO_MODE else None

    def add(self, name: str) -> Participant:
        """A new participant, on the lowest colour slot nobody in the room holds, from 1."""
        taken = {p.slot for p in self.participants.values()}
        slot = next(slot for slot in range(1, len(self.participants) + 2) if slot not in taken)
        participant = Participant(secrets.token_hex(8), name, slot)
        self.participants[participant.id] = participant
        self.changed()
        return participant

    @staticmethod
    def color_index(participant: Participant) -> int:
        """Shown as 1..9 (0 means "unknown")."""
        return 1 + (participant.slot - 1) % 9

    def peer(self, participant: Participant, state: Any) -> dict[str, Any]:
        return {"clientId": participant.id, "name": participant.name, "colorIndex": self.color_index(participant),
                "state": state}

    def roster(self, other_than: Participant) -> list[dict[str, Any]]:
        """Everyone else who has shared a retained presence."""
        return [self.peer(p, p.state) for p in self.participants.values() if p is not other_than and p.state is not None]

    def changed(self) -> None:
        """Demo only: the room's state for the Data panel (DEMO_MODE=true)."""
        if self._snapshot is not None:
            write_snapshot(self._snapshot, {"participants": len(self.participants), "values": self.values,
                                            "responseId": self.response_id})


_rooms: dict[str, FillRoom] = {}


async def join(key: str, seed: Callable[[], Awaitable[tuple[Any, dict[str, Any]]]]) -> FillRoom:
    """The open room, or a new one seeded with the definition and the saved answers."""
    room = _rooms.get(key)
    if room is None:
        definition, values = await seed()
        room = _rooms.setdefault(key, FillRoom(key, definition, values))   # another join may have opened it meanwhile
    if room.drop_timer is not None:   # back within 2 s: keep the room
        room.drop_timer.cancel()
        room.drop_timer = None
    return room


def leave(room: FillRoom, participant: Participant) -> None:
    """Drop the room 2 s after the last person leaves."""
    room.participants.pop(participant.id, None)
    room.changed()
    if not room.participants:
        room.drop_timer = asyncio.get_running_loop().call_later(2, _drop_if_empty, room)


def _drop_if_empty(room: FillRoom) -> None:
    if not room.participants and _rooms.get(room.key) is room:
        del _rooms[room.key]
