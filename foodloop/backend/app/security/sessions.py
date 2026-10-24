"""Login sessions stored in the database and referenced by an httpOnly cookie.

Why not a JWT in localStorage? JavaScript can read localStorage, so any script-injection bug could steal
logins. An httpOnly cookie is invisible to JavaScript, and deleting the session row logs the user out
everywhere immediately.
"""

import hashlib
import secrets
from datetime import timedelta

from fastapi import Response
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.clock import utcnow
from app.config import get_settings
from app.models import User, UserSession

COOKIE_NAME = "foodloop_session"
# Only write last_seen_at occasionally, not on every request.
_TOUCH_INTERVAL = timedelta(minutes=5)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            user_agent=(user_agent or "")[:255] or None,
            expires_at=utcnow() + timedelta(days=get_settings().session_days),
        )
    )
    db.commit()
    return token


def user_for_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    now = utcnow()
    if session is None or session.expires_at <= now:
        return None
    user = session.user
    if not user.is_active:
        return None
    if now - session.last_seen_at > _TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return user


def delete_session(db: Session, token: str | None) -> None:
    if token:
        db.execute(delete(UserSession).where(UserSession.token_hash == hash_token(token)))
        db.commit()


def delete_all_sessions(db: Session, user: User) -> None:
    db.execute(delete(UserSession).where(UserSession.user_id == user.id))


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=settings.session_days * 24 * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(COOKIE_NAME, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax")
