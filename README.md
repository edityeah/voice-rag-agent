# Voice RAG Agent — web edition

A real-time voice RAG assistant you can deploy on the web. Visitors sign in with
Google, get **15 minutes of conversation per 30 days**, upload their own
knowledge base, clone one or more voices, and talk to the agent right from the
dashboard.

## Features

- **Google sign-in + per-user quota** — 15 min / 30 days, enforced at token mint and via LiveKit token TTL.
- **Per-user knowledge base** — upload PDFs / `.txt` / `.md`; tick which docs the agent should reference for each call.
- **Multi-voice library** — record multiple samples, name them, preview TTS, and switch the active voice per user.
- **Free-tier deploy** — runs end-to-end on Neon + Render free + Hugging Face Space at $0/month, see [DEPLOY.md](DEPLOY.md).

## Architecture

```
Browser (HTML + livekit-client)
   │  Google SSO ──────────────►  FastAPI backend (server/)
   │  /api/me, /api/kb, /api/voices,  │
   │  /api/session/start              ├─► Cartesia (TTS + voice clone)
   │                                  └─► LiveKit (room + token)
   │  WebRTC audio
   ▼
LiveKit Cloud  ◄──────  voice_agent_openai.py worker
                         AssemblyAI (STT) → OpenAI (LLM + RAG over user's KB) → Cartesia (TTS)
```

- **server/main.py** — FastAPI app: Google OAuth, quota, LiveKit token mint, KB CRUD, voice CRUD, webhook receiver.
- **server/db.py** — SQLAlchemy models (`User`, `UsageEvent`, `Voice`, `KbDocument`). SQLite locally, Postgres in prod.
- **server/extract.py** — PDF / text extraction for uploaded KB documents.
- **server/cartesia_client.py** — voice clone + TTS preview wrapper.
- **voice_agent_openai.py** — LiveKit worker. Reads `voice_id` and `kb_doc_ids` from room metadata so each call uses that user's voice and selected docs.
- **voice_agent.py** — original Ollama implementation (kept for offline use).
- **web/** — single-page dashboard (`index.html`, `dashboard.html`, `app.js`, `styles.css`) — no build step.
- **huggingface-space/** — Dockerfile + README for deploying the worker on a free HF Space.
- **worker_runner.py** — entrypoint used by the HF Space container (adds a health endpoint alongside the LiveKit worker).
- **render.yaml** — Render Blueprint for the web backend.

## Local setup

### 1. Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Get credentials
You need accounts for:
- [OpenAI](https://platform.openai.com) — LLM + embeddings
- [Cartesia](https://play.cartesia.ai) — TTS + voice cloning (voice cloning needs a paid plan; TTS works on free)
- [Deepgram](https://deepgram.com) — STT
- [LiveKit Cloud](https://cloud.livekit.io) — WebRTC + agent worker
- [Google Cloud Console](https://console.cloud.google.com/apis/credentials) — OAuth 2.0 client. Add `http://localhost:8000/auth/callback` as an authorized redirect URI.

Copy `.env.example` to `.env` and fill in the values.

### 3. Run (two terminals)

**Terminal 1 — backend:**
```bash
uvicorn server.main:app --reload --port 8000
```

**Terminal 2 — voice agent worker:**
```bash
python voice_agent_openai.py dev
```

Then open http://localhost:8000 → sign in with Google → on the dashboard:
1. Upload one or more documents to your knowledge base.
2. (Optional) Record a 10–15 sec sample, name it, **Save voice**, then **Use this voice**.
3. Tick the docs you want the agent to reference, then click **Start call**.

### 4. (Optional) LiveKit webhook for accurate billing
The browser already reports session length to `/api/session/end`. For tighter
accuracy add a LiveKit webhook:
- Expose your local server: `ngrok http 8000`
- LiveKit Cloud → Settings → Webhooks → URL = `https://<ngrok>/livekit/webhook`

## How quota works
- Each user gets `QUOTA_SECONDS` (default 900 = 15 min) every `QUOTA_PERIOD_DAYS` (default 30).
- The window starts at first signup and rolls automatically once expired.
- `/api/session/start` refuses to mint a token when remaining = 0.
- LiveKit token TTL = remaining quota, so the room hard-stops on its own.

## Deploying on the web

The recommended path is the free-tier setup: Neon Postgres + Render free web + Hugging Face Space worker. Step-by-step instructions: [DEPLOY.md](DEPLOY.md).

Any container host also works — set all env vars from `.env.example`, switch `DATABASE_URL` to Postgres, point `PUBLIC_URL` at your deployed domain, and add that domain's `/auth/callback` to your Google OAuth client. The worker process is `python voice_agent_openai.py start` (or `python worker_runner.py` inside the HF Space container).

## Original (offline) implementation
The Ollama-based [voice_agent.py](voice_agent.py) still works for fully local
development. Run `ollama pull gemma3` first.
