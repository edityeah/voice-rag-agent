# Deployment guide — free tier (Neon + Render + Hugging Face)

Total cost: **$0/month**, no credit card required.

| Component | Where | Free tier |
|---|---|---|
| Postgres | Neon | 0.5 GB, auto-suspend |
| Web backend | Render | spins down after 15 min idle |
| Agent worker | Hugging Face Space | sleeps after 48 hr inactivity |

## 1. Create the Postgres database (Neon)

1. Go to https://console.neon.tech → sign up with GitHub
2. **New Project** → name it `voice-rag` → Create
3. On the dashboard, copy the **connection string** (looks like `postgresql://user:pass@ep-xxx.neon.tech/neondb?sslmode=require`)
4. Save it — you'll paste it as `DATABASE_URL` in two places.

## 2. Deploy the web backend (Render)

1. Go to https://dashboard.render.com → sign up with GitHub
2. **+ New** → **Blueprint**
3. Connect repo `edityeah/voice-rag-agent` → Apply
4. When prompted, fill in the env vars. Use the Neon connection string for `DATABASE_URL`. Leave `PUBLIC_URL` blank for now.
5. Wait for first deploy (~5 min). Note the URL: `https://voice-rag-web-xxxx.onrender.com`
6. Open **voice-rag-web** → **Environment** → set `PUBLIC_URL` to that URL → Save (auto-redeploys)
7. Update Google OAuth: console.cloud.google.com → your OAuth client → add `https://voice-rag-web-xxxx.onrender.com/auth/callback` to Authorized redirect URIs.

The web app is now live. Login + dashboard work, but **Start call** will fail until step 3 finishes.

## 3. Deploy the agent worker (Hugging Face Space)

1. Go to https://huggingface.co → sign up (free)
2. Top-right **+** → **New Space**
3. **Space name:** `voice-rag-agent-worker`
4. **License:** any (e.g. MIT)
5. **Space SDK:** **Docker** → choose **Blank**
6. **Hardware:** CPU basic (free)
7. **Visibility:** Public (or Private — both free)
8. Click **Create Space**

Now copy the two files from your repo's `huggingface-space/` folder into the new Space:

1. In the Space, click **Files** tab → **+ Add file** → **Create new file**
2. Filename: `README.md` → paste the contents of `huggingface-space/README.md` from your repo → Commit
3. **+ Add file** again → filename: `Dockerfile` → paste contents of `huggingface-space/Dockerfile` → Commit

The Space rebuilds automatically (takes ~5 min). Watch **Logs** tab.

Then **Settings → Variables and secrets** → add:

| Name | Value |
|---|---|
| `OPENAI_API_KEY` | your key |
| `CARTESIA_API_KEY` | your key |
| `DEEPGRAM_API_KEY` | your key |
| `LIVEKIT_URL` | your wss URL |
| `LIVEKIT_API_KEY` | your key |
| `LIVEKIT_API_SECRET` | your secret |
| `DATABASE_URL` | the same Neon connection string from step 1 |

After saving, the Space restarts. In Logs you should see `registered worker`.

## 4. Test

Open your Render URL → sign in → upload a doc → click Start call. The agent should join.

## Caveats and tips

- **Render free spin-down**: first request after 15 min idle takes ~30s. Subsequent requests are fast.
- **HF Space sleep after 48h**: worker stops if completely unused for 48 hours. To wake it, hit its Space URL in a browser. For active projects, this won't matter.
- **Neon auto-suspend**: DB pauses after a few minutes of no queries; first query after wakes it (~5s).
- **Keep Space awake**: optional — set up a cron-job.org free monthly job to ping the Space URL every 24h.
- **Updating code**: when you push to GitHub, the Render web redeploys automatically. The HF Space rebuilds on its own next push or when you click **Restart Space**, since the Dockerfile clones from GitHub at build time.
