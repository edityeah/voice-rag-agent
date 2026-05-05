"""LiveKit voice agent: AssemblyAI STT -> OpenAI LLM (with LlamaIndex RAG) -> Cartesia TTS.

Reads optional per-user voice_id from room metadata so each logged-in user can use
their cloned voice. Falls back to a default Cartesia voice.
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
from livekit.plugins import cartesia, deepgram, llama_index, silero

from llama_index.core import (
    Document,
    Settings,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.chat_engine.types import ChatMode
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.llms.openai import OpenAI

load_dotenv()
logger = logging.getLogger("voice-assistant")

DEFAULT_VOICE_ID = os.getenv(
    "CARTESIA_DEFAULT_VOICE_ID", "2b27d5e4-bcf9-496c-a54b-2ab64b0986b2"
)
PERSIST_DIR = os.getenv("RAG_PERSIST_DIR", "./chat-engine-storage-openai")
DOCS_DIR = os.getenv("RAG_DOCS_DIR", "docs")

Settings.llm = OpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
Settings.embed_model = OpenAIEmbedding(model="text-embedding-3-small")


def _read_docs(docs_dir: str) -> list:
    """Load .pdf, .txt, .md files into Documents without SimpleDirectoryReader."""
    documents = []
    for root, _, files in os.walk(docs_dir):
        for fname in files:
            path = os.path.join(root, fname)
            ext = fname.lower().rsplit(".", 1)[-1]
            try:
                if ext == "pdf":
                    from pypdf import PdfReader
                    reader = PdfReader(path)
                    text = "\n".join((p.extract_text() or "") for p in reader.pages)
                elif ext in ("txt", "md"):
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                else:
                    continue
                if text.strip():
                    documents.append(Document(text=text, metadata={"source": fname}))
            except Exception as e:
                logging.warning("Skipping %s: %s", path, e)
    return documents


def _load_index():
    if not os.path.exists(PERSIST_DIR) or not os.listdir(PERSIST_DIR):
        documents = _read_docs(DOCS_DIR)
        if not documents:
            documents = [Document(text="No documents loaded. Answer from general knowledge.")]
        index = VectorStoreIndex.from_documents(documents)
        index.storage_context.persist(persist_dir=PERSIST_DIR)
        return index
    storage_context = StorageContext.from_defaults(persist_dir=PERSIST_DIR)
    return load_index_from_storage(storage_context)


# Loaded lazily on first job to avoid embedding-model rebuild during import.
_index = None


def _get_index():
    global _index
    if _index is None:
        _index = _load_index()
    return _index


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


def _parse_metadata(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


async def entrypoint(ctx: JobContext):
    chat_context = ChatContext().append(
        role="system",
        text=(
            "You are a friendly, concise voice assistant grounded in the provided documents. "
            "Answer in short spoken-style sentences. Avoid emojis and unpronounceable punctuation."
        ),
    )

    chat_engine = _get_index().as_chat_engine(chat_mode=ChatMode.CONTEXT)
    logger.info("Connecting to room %s", ctx.room.name)
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    participant = await ctx.wait_for_participant()
    logger.info("Starting voice assistant for participant %s", participant.identity)

    metadata = _parse_metadata(ctx.room.metadata) or _parse_metadata(participant.metadata)
    voice_id = metadata.get("voice_id") or DEFAULT_VOICE_ID
    logger.info("Using voice_id=%s", voice_id)

    agent = VoicePipelineAgent(
        vad=ctx.proc.userdata["vad"],
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=llama_index.LLM(chat_engine=chat_engine),
        tts=cartesia.TTS(model="sonic-2", voice=voice_id),
        chat_ctx=chat_context,
    )

    agent.start(ctx.room, participant)
    await agent.say("Hey there! How can I help you today?", allow_interruptions=True)


if __name__ == "__main__":
    print("Starting voice agent (OpenAI)...")
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
