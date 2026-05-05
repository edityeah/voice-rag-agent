"""Mint LiveKit access tokens with per-user metadata."""
import json
import os
from datetime import timedelta

from livekit import api

LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "")


def make_join_token(*, identity: str, room: str, ttl_seconds: int, metadata: dict) -> str:
    if not (LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise RuntimeError("LiveKit credentials not configured")
    grants = api.VideoGrants(
        room_join=True,
        room=room,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=True,
    )
    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name(identity)
        .with_grants(grants)
        .with_metadata(json.dumps(metadata))
        .with_ttl(timedelta(seconds=ttl_seconds))
    )
    return token.to_jwt()


async def update_room_metadata(room: str, metadata: dict) -> None:
    """Set room metadata so the agent can read voice_id when it joins."""
    if not (LIVEKIT_API_KEY and LIVEKIT_API_SECRET and LIVEKIT_URL):
        return
    lkapi = api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    try:
        await lkapi.room.update_room_metadata(
            api.UpdateRoomMetadataRequest(room=room, metadata=json.dumps(metadata))
        )
    except Exception:
        pass
    finally:
        await lkapi.aclose()
