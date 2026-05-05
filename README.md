# Voice RAG Agent — web edition

A real-time voice RAG assistant you can deploy on the web. Visitors sign in with
Google, get **15 minutes of conversation per 30 days**, can clone their own
voice, and talk to the agent right from the dashboard.

## Architecture

```
Browser (HTML + livekit-client)
   │  Google SSO ──────────────►  FastAPI backend (server/)
   │  /api/me, /api/session/start    │
   │                                 ├─► Cartesia (TTS + voice clone)
   │                                 └─► LiveKit (room + token)
   │  WebRTC audio
   ▼
LiveKit Cloud  ◄──────  voice_agent_openai.py worker
                         AssemblyAI (STT) → OpenAI (LLM + RAG over docs/) → Cartesia (TTS)
```

- **server/main.py** — FastAPI app: Google OAuth, quota enforcement, LiveKit token mint, voice CRUD, webhook receiver.
- **voice_agent_openai.py** — LiveKit worker. Reads `voice_id` from room metadata so each user gets their own cloned voice.
- **voice_agent.py** — original Ollama implementation (kept for offline use).
- **web/** — single-page dashboard (no build step).

## Local setup

### 1. Install
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Get credentials
You need accounts for:
- [OpenAI](https://platform.openai.com) — LLM + embeddings
- [Cartesia](https://play.cartesia.ai) — TTS + voice cloning
- [AssemblyAI](https://www.assemblyai.com) — STT
- [LiveKit Cloud](https://cloud.livekit.io) — WebRTC + agent worker
- [Google Cloud Console](https://console.cloud.google.com/apis/credentials) — OAuth 2.0 client. Add `http://localhost:8000/auth/callback` as an authorized redirect URI.

Copy `.env.example` to `.env` and fill in the values.

### 3. Run (three terminals)

**Terminal 1 — backend:**
```bash
uvicorn server.main:app --reload --port 8000
```

**Terminal 2 — voice agent worker:**
```bash
python voice_agent_openai.py dev
```

**Terminal 3 — open the app:**
```
http://localhost:8000
```

Sign in with Google → land on the dashboard → record a 10–15 sec voice sample → click **Clone & save** → click **Start call**.

### 4. (Optional) LiveKit webhook for accurate billing
The browser already reports session length to `/api/session/end`. For more
accuracy add a LiveKit webhook:
- Expose your local server: `ngrok http 8000`
- LiveKit Cloud → Settings → Webhooks → URL = `https://<ngrok>/livekit/webhook`

## How quota works
- Each user gets `QUOTA_SECONDS` (default 900 = 15 min) every `QUOTA_PERIOD_DAYS` (default 30).
- The 30-day window starts at first signup and rolls automatically once expired.
- `/api/session/start` refuses to mint a token when remaining = 0.
- LiveKit token TTL = remaining quota, so the room hard-stops on its own.

## Deploying on the web
- Backend: any container host (Railway / Render / Fly). Set all env vars; switch `DATABASE_URL` to Postgres.
- Worker: same host or a separate process — `python voice_agent_openai.py start`.
- Update Google OAuth redirect URI to your production `PUBLIC_URL`.

## Files added in this iteration
- `server/` — FastAPI app, DB models, Cartesia + LiveKit clients, Google OAuth.
- `web/` — `index.html`, `dashboard.html`, `app.js`, `styles.css`.
- `voice_agent_openai.py` — cloud-friendly variant of the agent.
- Updated `requirements.txt` and `.env.example`.

## Original (offline) implementation
The Ollama-based [voice_agent.py](voice_agent.py) still works for fully local
development. Run `ollama pull gemma3` first.
