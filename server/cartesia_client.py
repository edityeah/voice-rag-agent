"""Thin wrapper around Cartesia's voice clone API."""
import os
import httpx

CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY", "")
CARTESIA_API_BASE = "https://api.cartesia.ai"
CARTESIA_VERSION = "2024-06-10"


async def clone_voice(audio_bytes: bytes, filename: str, name: str) -> dict:
    """Upload an audio sample to Cartesia and return the created voice payload."""
    if not CARTESIA_API_KEY:
        raise RuntimeError("CARTESIA_API_KEY not set")

    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": CARTESIA_VERSION,
    }
    files = {"clip": (filename, audio_bytes, "audio/wav")}
    data = {
        "name": name,
        "language": "en",
        "mode": "stability",
        "enhance": "true",
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            f"{CARTESIA_API_BASE}/voices/clone",
            headers=headers,
            files=files,
            data=data,
        )
        r.raise_for_status()
        return r.json()


async def delete_voice(voice_id: str) -> None:
    if not CARTESIA_API_KEY or not voice_id:
        return
    headers = {"X-API-Key": CARTESIA_API_KEY, "Cartesia-Version": CARTESIA_VERSION}
    async with httpx.AsyncClient(timeout=30.0) as client:
        await client.delete(f"{CARTESIA_API_BASE}/voices/{voice_id}", headers=headers)


async def tts_preview(voice_id: str, text: str) -> bytes:
    """Synthesize a short preview clip for the dashboard. Returns WAV bytes."""
    if not CARTESIA_API_KEY:
        raise RuntimeError("CARTESIA_API_KEY not set")
    headers = {
        "X-API-Key": CARTESIA_API_KEY,
        "Cartesia-Version": CARTESIA_VERSION,
        "Content-Type": "application/json",
    }
    payload = {
        "model_id": "sonic-2",
        "transcript": text,
        "voice": {"mode": "id", "id": voice_id},
        "output_format": {
            "container": "wav",
            "encoding": "pcm_s16le",
            "sample_rate": 24000,
        },
        "language": "en",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        r = await client.post(
            f"{CARTESIA_API_BASE}/tts/bytes", headers=headers, json=payload
        )
        r.raise_for_status()
        return r.content
