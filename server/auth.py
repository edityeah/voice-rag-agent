"""Google OAuth + JWT session cookie helpers."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Cookie, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import SessionLocal, User, utcnow

JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-me")
JWT_ALG = "HS256"
SESSION_COOKIE = "va_session"
SESSION_DAYS = 7


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def issue_session_token(user: User) -> str:
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "exp": datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_session_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        return None


def current_user(
    request: Request,
    db: Session = Depends(get_db),
    va_session: Optional[str] = Cookie(default=None),
) -> User:
    token = va_session
    if not token:
        auth = request.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="not authenticated")
    payload = decode_session_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="invalid session")
    user = db.get(User, int(payload["sub"]))
    if not user:
        raise HTTPException(status_code=401, detail="user not found")
    return user


def upsert_google_user(db: Session, info: dict) -> User:
    sub = info["sub"]
    user = db.query(User).filter(User.google_sub == sub).first()
    if user:
        user.name = info.get("name", user.name)
        user.picture = info.get("picture", user.picture)
        db.commit()
        return user
    user = User(
        google_sub=sub,
        email=info["email"],
        name=info.get("name"),
        picture=info.get("picture"),
        period_start=utcnow(),
        seconds_used=0,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
