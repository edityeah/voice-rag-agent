"""LiveKit voice agent: Deepgram STT -> OpenAI LLM (per-user RAG) -> Cartesia TTS.

Per call:
- Reads user_id and voice_id from room metadata.
- Loads that user's uploaded documents from Postgres/SQLite.
- Builds an in-memory vector index for the call.
- If the user has no docs, falls back to a generic chat (no RAG).
"""
import json
import logging
import os
from typing import Optional

from dotenv import load_dotenv
from livekit.agents import JobContext, JobProcess, WorkerOptions, cli
from livekit.agents.job import AutoSubscribe
from livekit.agents.llm import ChatContext
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import cartesia, deepgram, llama_index as lk_llama, openai as lk_openai, silero

from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.chat_engine.types import ChatMode
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

load_dotenv()
logger = logging.getLogger("voice-assistant")

DEFAULT_VOICE_ID = os.getenv(
    "CARTESIA_DEFAULT_VOICE_ID", "2b27d5e4-bcf9-496c-a54b-2ab64b0986b2"
)
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

Settings.llm = OpenAI(model=OPENAI_MODEL)
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")


def _parse_metadata(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def _load_user_docs(user_id: int):
    """Fetch this user's uploaded documents from the DB."""
    from server.db import KbDocument, SessionLocal
    db = SessionLocal()
    try:
        rows = db.query(KbDocument).filter(KbDocument.user_id == user_id).all()
        return [
            Document(text=r.content, metadata={"source": r.filename}) for r in rows
        ]
    finally:
        db.close()


def _build_chat_engine(user_id: Optional[int]):
    """Build a chat engine over the user's docs. Returns None if no docs."""
    if not user_id:
        return None
    docs = _load_user_docs(user_id)
    if not docs:
        return None
    logger.info("Building index from %d documents for user %s", len(docs), user_id)
    index = VectorStoreIndex.from_documents(docs)
    return index.as_chat_engine(chat_mode=ChatMode.CONTEXT)


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    logger.info("Connecting to room %s", ctx.room.name)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    logger.info("Starting voice assistant for participant %s", participant.identity)

    metadata = _parse_metadata(ctx.room.metadata) or _parse_metadata(participant.metadata)
    user_id = metadata.get("user_id")
    voice_id = metadata.get("voice_id") or DEFAULT_VOICE_ID
    logger.info("user_id=%s voice_id=%s", user_id, voice_id)

    chat_engine = _build_chat_engine(user_id) if user_id else None

    if chat_engine is not None:
        system_text = (
            "You are a friendly, concise voice assistant. Answer the user's questions "
            "based on the documents they have uploaded. Keep answers short and spoken-style. "
            "Avoid emojis and unpronounceable punctuation."
        )
        llm = lk_llama.LLM(chat_engine=chat_engine)
        greeting = "Hey! I have your documents loaded. What would you like to know?"
    else:
        system_text = (
            "You are a friendly, concise voice assistant. The user has not uploaded any "
            "documents yet, so answer from general knowledge. Keep answers short and "
            "spoken-style. Avoid emojis and unpronounceable punctuation."
        )
        llm = lk_openai.LLM(model=OPENAI_MODEL)
        greeting = (
            "Hey there! You haven't uploaded any documents yet, so I'll answer from "
            "general knowledge. What can I help you with?"
        )

    chat_context = ChatContext().append(role="system", text=system_text)

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=llm,
        tts=cartesia.TTS(model="sonic-2", voice=voice_id),
        chat_ctx=chat_context,
    )

    agent.start(ctx.room, participant)
    await agent.say(greeting, allow_interruptions=True)


if __name__ == "__main__":
    print("Starting voice agent (OpenAI)...")
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
