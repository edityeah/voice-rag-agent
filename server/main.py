"""FastAPI backend for the Voice RAG Agent web app.

- Google SSO login (Authlib)
- 15 min / 30 day quota per user
- LiveKit join-token minting (refuses if quota exhausted)
- Voice cloning via Cartesia
- LiveKit webhook receiver to track real session duration
"""
import json
import os
import secrets
from pathlib import Path

from authlib.integrations.starlette_client import OAuth, OAuthError
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from livekit import api as lkapi
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import cartesia_client
from .auth import (
    SESSION_COOKIE,
    SESSION_DAYS,
    current_user,
    get_db,
    issue_session_token,
    upsert_google_user,
)
from .db import QUOTA_PERIOD_DAYS, QUOTA_SECONDS, UsageEvent, User, init_db
from .livekit_client import LIVEKIT_URL, make_join_token, update_room_metadata

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
SESSION_SECRET = os.getenv("SESSION_SECRET", secrets.token_urlsafe(32))
LIVEKIT_WEBHOOK_KEY = os.getenv("LIVEKIT_API_KEY", "")
LIVEKIT_WEBHOOK_SECRET = os.getenv("LIVEKIT_API_SECRET", "")
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost:8000")

app = FastAPI(title="Voice RAG Agent")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, https_only=False)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[PUBLIC_URL, "http://localhost:8000", "http://127.0.0.1:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@app.on_event("startup")
def _startup():
    init_db()


# ---------- Auth ----------
@app.get("/auth/login")
async def login(request: Request):
    redirect_uri = f"{PUBLIC_URL}/auth/callback"
    return await oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError as e:
        raise HTTPException(status_code=400, detail=f"OAuth error: {e.error}")
    info = token.get("userinfo") or await oauth.google.parse_id_token(request, token)
    user = upsert_google_user(db, info)
    session_jwt = issue_session_token(user)
    resp = RedirectResponse(url="/dashboard")
    resp.set_cookie(
        key=SESSION_COOKIE,
        value=session_jwt,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
    )
    return resp


@app.post("/auth/logout")
async def logout():
    resp = RedirectResponse(url="/", status_code=303)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ---------- User / Quota ----------
@app.get("/api/me")
def me(user: User = Depends(current_user)):
    user.roll_period_if_needed()
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "quota": {
            "limit_seconds": QUOTA_SECONDS,
            "period_days": QUOTA_PERIOD_DAYS,
            "seconds_used": user.seconds_used,
            "seconds_remaining": user.remaining_seconds(),
            "period_start": user.period_start.isoformat(),
            "resets_at": user.period_resets_at().isoformat(),
        },
        "voice": {
            "id": user.custom_voice_id,
            "name": user.custom_voice_name,
        },
    }


@app.get("/api/usage")
def usage(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == user.id)
        .order_by(UsageEvent.started_at.desc())
        .limit(30)
        .all()
    )
    return [
        {
            "room": r.room_name,
            "started_at": r.started_at.isoformat(),
            "duration_seconds": r.duration_seconds,
        }
        for r in rows
    ]


# ---------- LiveKit token ----------
@app.post("/api/session/start")
async def start_session(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    user.roll_period_if_needed()
    remaining = user.remaining_seconds()
    if remaining <= 0:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "quota_exhausted",
                "resets_at": user.period_resets_at().isoformat(),
            },
        )

    room_name = f"u{user.id}-{secrets.token_hex(4)}"
    voice_id = user.custom_voice_id or os.getenv(
        "CARTESIA_DEFAULT_VOICE_ID", "2b27d5e4-bcf9-496c-a54b-2ab64b0986b2"
    )
    metadata = {"user_id": user.id, "voice_id": voice_id}

    # TTL = remaining quota, capped at 15 minutes
    ttl = min(remaining, QUOTA_SECONDS)
    token = make_join_token(
        identity=f"user-{user.id}",
        room=room_name,
        ttl_seconds=ttl,
        metadata=metadata,
    )

    db.add(UsageEvent(user_id=user.id, room_name=room_name, duration_seconds=0))
    db.commit()

    # Best-effort: set room metadata so agent reads voice_id even if it joins first
    await update_room_metadata(room_name, metadata)

    return {
        "token": token,
        "url": LIVEKIT_URL,
        "room": room_name,
        "ttl_seconds": ttl,
        "voice_id": voice_id,
    }


# ---------- Voice management ----------
@app.post("/api/voice/clone")
async def clone_voice(
    name: str = Form(...),
    sample: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    audio = await sample.read()
    if len(audio) < 1024:
        raise HTTPException(status_code=400, detail="audio sample too short")
    if user.custom_voice_id:
        await cartesia_client.delete_voice(user.custom_voice_id)
    result = await cartesia_client.clone_voice(audio, sample.filename or "sample.wav", name)
    voice_id = result.get("id") or result.get("voice_id")
    if not voice_id:
        raise HTTPException(status_code=502, detail="Cartesia did not return a voice id")
    user.custom_voice_id = voice_id
    user.custom_voice_name = name
    db.commit()
    return {"voice_id": voice_id, "name": name}


@app.post("/api/voice/preview")
async def preview_voice(
    payload: dict, user: User = Depends(current_user)
):
    voice_id = payload.get("voice_id") or user.custom_voice_id
    text = payload.get("text") or "Hello! This is a quick preview of your voice."
    if not voice_id:
        raise HTTPException(status_code=400, detail="no voice configured")
    audio = await cartesia_client.tts_preview(voice_id, text[:300])
    return Response(content=audio, media_type="audio/wav")


@app.delete("/api/voice")
async def delete_voice(
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    if user.custom_voice_id:
        await cartesia_client.delete_voice(user.custom_voice_id)
    user.custom_voice_id = None
    user.custom_voice_name = None
    db.commit()
    return {"ok": True}


# ---------- LiveKit webhook ----------
@app.post("/livekit/webhook")
async def livekit_webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    auth_header = request.headers.get("Authorization", "")
    try:
        receiver = lkapi.WebhookReceiver(
            lkapi.TokenVerifier(LIVEKIT_WEBHOOK_KEY, LIVEKIT_WEBHOOK_SECRET)
        )
        event = receiver.receive(body.decode(), auth_header)
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"invalid webhook: {e}")

    if event.event in ("room_finished", "participant_left"):
        room_name = getattr(event.room, "name", None) if event.room else None
        if not room_name:
            return {"ok": True}
        ev = (
            db.query(UsageEvent)
            .filter(UsageEvent.room_name == room_name)
            .order_by(UsageEvent.id.desc())
            .first()
        )
        if not ev:
            return {"ok": True}
        # Use room duration from the event when available
        duration = 0
        if event.room and getattr(event.room, "creation_time", 0):
            from time import time as _time
            duration = max(0, int(_time()) - int(event.room.creation_time))
        if duration > QUOTA_SECONDS:
            duration = QUOTA_SECONDS
        if ev.duration_seconds == 0 and duration > 0:
            ev.duration_seconds = duration
            user = db.get(User, ev.user_id)
            if user:
                user.roll_period_if_needed()
                user.seconds_used = min(QUOTA_SECONDS, user.seconds_used + duration)
            db.commit()
    return {"ok": True}


# ---------- Client-side fallback usage report ----------
@app.post("/api/session/end")
def end_session(
    payload: dict,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Browser pings this on disconnect so we still track usage without a webhook."""
    room = payload.get("room")
    duration = int(payload.get("duration_seconds", 0))
    if not room or duration <= 0:
        return {"ok": True}
    ev = (
        db.query(UsageEvent)
        .filter(UsageEvent.room_name == room, UsageEvent.user_id == user.id)
        .order_by(UsageEvent.id.desc())
        .first()
    )
    if not ev or ev.duration_seconds > 0:
        return {"ok": True}
    agent_joined = bool(payload.get("agent_joined"))
    # If the agent never joined, don't bill — likely a worker error.
    if not agent_joined or duration < 5:
        ev.duration_seconds = 0
        db.commit()
        return {"ok": True, "billed": False, "seconds_remaining": user.remaining_seconds()}
    duration = min(duration, QUOTA_SECONDS)
    ev.duration_seconds = duration
    user.roll_period_if_needed()
    user.seconds_used = min(QUOTA_SECONDS, user.seconds_used + duration)
    db.commit()
    return {"ok": True, "seconds_remaining": user.remaining_seconds()}


# ---------- Static frontend ----------
WEB_DIR = Path(__file__).resolve().parent.parent / "web"
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def landing():
    return (WEB_DIR / "index.html").read_text()


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (WEB_DIR / "dashboard.html").read_text()
