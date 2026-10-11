from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import current_user_optional
from app.config import get_settings
from app.db import get_db
from app.errors import DomainError
from app.models import User
from app.models.enums import UserRole
from app.schemas.auth import LoginRequest, MeResponse, ProviderOut, ProviderRegisterRequest, RegisterRequest, UserOut
from app.security.rate_limit import limiter
from app.security.sessions import COOKIE_NAME, clear_session_cookie, create_session, delete_session, set_session_cookie
from app.services import accounts
from app.services.providers import provider_for_user

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_rate(key: str, limit: int, window_minutes: int) -> None:
    if not limiter.hit(key, limit, window_minutes * 60):
        raise DomainError(429, f"Too many attempts. Please wait {window_minutes} minutes and try again.")


def me_response(db: Session, user: User) -> MeResponse:
    provider = provider_for_user(db, user) if user.role == UserRole.provider else None
    return MeResponse(
        user=UserOut.model_validate(user),
        provider=ProviderOut.model_validate(provider) if provider else None,
    )


def _start_session(db: Session, request: Request, response: Response, user: User) -> MeResponse:
    token = create_session(db, user, request.headers.get("user-agent"))
    set_session_cookie(response, token)
    return me_response(db, user)


@router.post("/register", response_model=MeResponse, status_code=201)
def register(data: RegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    """Create a customer account and log in."""
    _check_rate(f"register:{_client_ip(request)}", 20, 60)
    user = accounts.register_customer(db, data)
    return _start_session(db, request, response, user)


@router.post("/register-provider", response_model=MeResponse, status_code=201)
def register_provider(
    data: ProviderRegisterRequest, request: Request, response: Response, db: Session = Depends(get_db)
):
    """Create a provider account plus its kitchen. The kitchen stays `pending` until an admin approves it."""
    _check_rate(f"register:{_client_ip(request)}", 20, 60)
    user, _ = accounts.register_provider(db, data)
    return _start_session(db, request, response, user)


@router.post("/login", response_model=MeResponse)
def login(data: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    settings = get_settings()
    _check_rate(
        f"login:{_client_ip(request)}:{data.email}",
        settings.login_attempts_per_window,
        settings.login_window_minutes,
    )
    user = accounts.authenticate(db, data.email, data.password)
    return _start_session(db, request, response, user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: Session = Depends(get_db)) -> None:
    delete_session(db, request.cookies.get(COOKIE_NAME))
    clear_session_cookie(response)


@router.get("/me", response_model=MeResponse | None)
def me(user: User | None = Depends(current_user_optional), db: Session = Depends(get_db)):
    """The logged-in user, or null. Returns 200 either way so the website can check quietly."""
    return me_response(db, user) if user else None
