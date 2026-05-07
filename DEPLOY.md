# Deployment guide — free tier (Neon + Render + Hugging Face)

Total cost: **$0/month**. No credit card required for the worker host.

| Component | Where | Free tier |
|---|---|---|
| Postgres | Neon | 0.5 GB, auto-suspend |
| Web backend | Render | spins down after 15 min idle |
| Agent worker | Hugging Face Space | sleeps after 48 h inactivity |

The web backend serves the dashboard and mints LiveKit tokens. The worker
process (`voice_agent_openai.py`) opens an outbound connection to LiveKit
Cloud and joins each user's room when a call starts. They are independent
services that share the same Postgres database.

## 1. Create the Postgres database (Neon)

1. Go to https://console.neon.tech → sign up with GitHub.
2. **New Project** → name it `voice-rag` → Create.
3. Copy the **connection string** — looks like
   `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`.
4. You'll paste this as `DATABASE_URL` in both Render (web) and Hugging
   Face (worker).

## 2. Deploy the web backend (Render)

1. Go to https://dashboard.render.com → sign up with GitHub.
2. **+ New** → **Blueprint** → connect repo `edityeah/voice-rag-agent` → Apply.
3. Fill in env vars when prompted. Use the Neon connection string for
   `DATABASE_URL`. Leave `PUBLIC_URL` blank for now.
4. Wait ~5 min for first deploy. Note the URL: `https://voice-rag-web-xxxx.onrender.com`.
5. **voice-rag-web** → **Environment** → set `PUBLIC_URL` to that URL → Save (auto-redeploys).
6. Update Google OAuth: console.cloud.google.com → your OAuth client →
   add `https://voice-rag-web-xxxx.onrender.com/auth/callback` to **Authorized redirect URIs**.

The web app is now live. Login + dashboard work, but **Start call** will fail
until step 3 finishes — there's no worker registered yet.

## 3. Deploy the agent worker (Hugging Face Space)

1. Go to https://huggingface.co → sign up (free, no card required).
2. Top-right **+** → **New Space**.
3. Fill in:
   - **Owner**: your username
   - **Space name**: `voice-rag-agent-worker`
   - **License**: any (e.g. MIT)
   - **Space SDK**: **Docker** → choose **Blank**
   - **Hardware**: **CPU basic** (free)
   - **Visibility**: Public or Private (both free)
4. Click **Create Space**.

Now copy the two files from this repo's `huggingface-space/` folder into the
new Space:

1. In the Space, click the **Files** tab → **+ Add file** → **Create new file**.
2. **Filename**: `README.md` → paste the contents of
   [`huggingface-space/README.md`](huggingface-space/README.md) → Commit.
3. **+ Add file** again → **Filename**: `Dockerfile` → paste the contents of
   [`huggingface-space/Dockerfile`](huggingface-space/Dockerfile) → Commit.

The Space rebuilds automatically (~5 min). Watch the **Logs** tab.

Then **Settings → Variables and secrets** → add:

| Name | Value |
|---|---|
| `OPENAI_API_KEY` | your key |
| `OPENAI_MODEL` | `gpt-4o-mini` |
| `CARTESIA_API_KEY` | your key |
| `CARTESIA_DEFAULT_VOICE_ID` | `2b27d5e4-bcf9-496c-a54b-2ab64b0986b2` |
| `DEEPGRAM_API_KEY` | your key |
| `LIVEKIT_URL` | your wss URL |
| `LIVEKIT_API_KEY` | your key |
| `LIVEKIT_API_SECRET` | your secret |
| `DATABASE_URL` | the same Neon connection string from step 1 |

After saving, the Space restarts. In **Logs** you should see
`registered worker  id=AW_...` near the bottom. That's the worker saying
"I'm available" to LiveKit Cloud.

## 4. Test

Open your Render URL → sign in → upload a doc → click **Start call**. The
agent should join within ~2 seconds.

## 5. (Recommended) Keep the Space awake

By default the Space sleeps after 48 h of inactivity, which means a cold start
on your first call after a long gap (~30 s wait, occasional rebuild that breaks
silently if you're unlucky).

Set up a free uptime pinger to ping the Space every 6 h:

1. Go to https://cron-job.org → sign up.
2. **Cronjobs → Create cronjob**.
3. **Title**: `voice-rag-worker keepalive`.
4. **URL**: your Space's public URL, which is
   `https://<your-username>-voice-rag-agent-worker.hf.space/`. The worker
   exposes a `/` health endpoint that returns `agent worker running`.
5. **Schedule**: every 6 hours.
6. Save.

This costs nothing and prevents the sleep-then-rebuild path that has historically
caused silent breakage.

## Caveats

- **Render free spin-down**: first dashboard request after 15 min idle takes
  ~30 s. Subsequent requests are fast.
- **Neon auto-suspend**: DB pauses after a few minutes of no queries; first
  query wakes it (~5 s).
- **HF Space rebuild**: when the Space is restarted (manually or by HF
  maintenance), the Dockerfile re-clones the repo from GitHub and reinstalls
  `requirements.txt`. As long as `requirements.txt` is correct (it is, in
  this repo's current state), this is safe and reproducible.
- **Updating code**: Render redeploys automatically on `git push`. The HF
  Space rebuilds when you push to its own repo, click **Restart Space**, or
  add the Dockerfile / README again — easiest is **Settings → Factory
  rebuild** after pushing to GitHub.
