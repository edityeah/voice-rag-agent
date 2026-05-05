---
title: Voice RAG Agent Worker
emoji: 🎤
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Voice RAG Agent — LiveKit worker

This Space runs the agent worker for the Voice RAG Agent project.
It registers with LiveKit Cloud and waits for incoming voice calls.

The web frontend lives elsewhere (e.g. on Render) and shares the same Postgres database.

## Setup

In the Space's **Settings → Variables and secrets**, add:

| Name | Value |
|---|---|
| `OPENAI_API_KEY` | from platform.openai.com |
| `CARTESIA_API_KEY` | from play.cartesia.ai |
| `DEEPGRAM_API_KEY` | from console.deepgram.com |
| `LIVEKIT_URL` | wss://your-project.livekit.cloud |
| `LIVEKIT_API_KEY` | from cloud.livekit.io |
| `LIVEKIT_API_SECRET` | from cloud.livekit.io |
| `DATABASE_URL` | your Neon Postgres connection string |

The Space will rebuild automatically and the worker registers within a minute.
