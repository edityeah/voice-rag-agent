# Deployment guide

| Component | Where | Cost |
|---|---|---|
| Postgres | Neon | free (0.5 GB, auto-suspend) |
| Web backend | Render | free (spins down after 15 min idle) |
| Agent worker | Fly.io | ~$0/mo on hobby plan credit (CC required for verification) |

The web backend serves the dashboard and mints LiveKit tokens. The worker process
(`voice_agent_openai.py`) opens an outbound connection to LiveKit Cloud and joins
each user's room when a call starts. They are independent services that share
the same Postgres database.

## 1. Create the Postgres database (Neon)

1. Go to https://console.neon.tech → sign up with GitHub.
2. **New Project** → name it `voice-rag` → Create.
3. Copy the **connection string** — looks like
   `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`.
4. You'll paste this as `DATABASE_URL` in both Render (web) and Fly (worker).

## 2. Deploy the web backend (Render)

1. Go to https://dashboard.render.com → sign up with GitHub.
2. **+ New** → **Blueprint** → connect repo `edityeah/voice-rag-agent` → Apply.
3. Fill in the env vars when prompted. Use the Neon connection string for
   `DATABASE_URL`. Leave `PUBLIC_URL` blank for now.
4. Wait ~5 min for the first deploy. Note the URL: `https://voice-rag-web-xxxx.onrender.com`.
5. **voice-rag-web** → **Environment** → set `PUBLIC_URL` to that URL → Save (auto-redeploys).
6. Update Google OAuth: console.cloud.google.com → your OAuth client →
   add `https://voice-rag-web-xxxx.onrender.com/auth/callback` to **Authorized redirect URIs**.

The web app is now live. Login + dashboard work, but **Start call** will fail
until step 3 finishes — there's no worker registered yet.

## 3. Deploy the agent worker (Fly.io)

### One-time setup

1. Sign up at https://fly.io (credit card required for verification — you won't
   be charged for this workload).
2. Install the CLI:
   ```bash
   brew install flyctl       # macOS
   # or: curl -L https://fly.io/install.sh | sh
   ```
3. Log in: `fly auth login`.

### Launch the app

From the repo root (where `fly.toml` lives):

```bash
fly launch --no-deploy --copy-config
```

When prompted:
- **App name**: pick anything (e.g. `voice-rag-worker-aditya`). The default in
  `fly.toml` is `voice-rag-worker` — if that's taken, Fly will suggest a unique
  name and update the file.
- **Region**: `bom` (Mumbai) is preselected; pick your closest region.
- **Postgres / Redis**: skip both — we use Neon.
- **Deploy now?**: **No** — we need to set secrets first.

### Set secrets

```bash
fly secrets set \
  OPENAI_API_KEY=sk-... \
  CARTESIA_API_KEY=... \
  CARTESIA_DEFAULT_VOICE_ID=2b27d5e4-bcf9-496c-a54b-2ab64b0986b2 \
  DEEPGRAM_API_KEY=... \
  LIVEKIT_URL=wss://your-project.livekit.cloud \
  LIVEKIT_API_KEY=... \
  LIVEKIT_API_SECRET=... \
  DATABASE_URL='postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require' \
  OPENAI_MODEL=gpt-4o-mini
```

Use the **same** `DATABASE_URL` as Render. Worker reads each user's KB from
Postgres at call start.

### Deploy

```bash
fly deploy
```

First build takes ~5 min. After it finishes, verify the worker registered:

```bash
fly logs
```

You should see a line like `registered worker  id=AW_...`. That's the worker
saying "I'm available" to LiveKit Cloud.

### Test

Open your Render URL → sign in → upload a doc → click **Start call**.
The agent should join within ~2 seconds.

## 4. (Optional) Auto-deploy on git push

Render redeploys the web app automatically when you push to `main`. To get the
same for the Fly worker, add a GitHub Actions workflow that runs `fly deploy`:

```yaml
# .github/workflows/fly-deploy.yml
name: Fly Deploy
on:
  push:
    branches: [main]
    paths:
      - 'voice_agent_openai.py'
      - 'server/**'
      - 'requirements.txt'
      - 'Dockerfile'
      - 'fly.toml'
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}
```

Generate a token with `fly tokens create deploy` and add it to GitHub repo
**Settings → Secrets and variables → Actions** as `FLY_API_TOKEN`.

## Caveats

- **Render free spin-down**: first request to the dashboard after 15 min idle
  takes ~30 s. Subsequent requests are fast.
- **Neon auto-suspend**: DB pauses after a few minutes of no queries; first
  query after wakes it (~5 s).
- **Fly machine sizing**: 512 MB is enough for this workload (Silero VAD +
  in-memory vector index over a few KB documents). If you upload very large
  PDFs, bump `memory_mb` in `fly.toml`.
- **Updating code**: `git push` auto-redeploys Render. The Fly worker
  redeploys via `fly deploy` (manual) or the GitHub Action above (automatic).
- **Cost watch**: `fly status` shows machine state. The hobby-plan $5 credit
  comfortably covers one shared-cpu-1x machine running 24/7.
