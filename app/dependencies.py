from fastapi import Depends, Request
from sqlalchemy.orm import Session
from .database import get_db
from .models import Member
from .i18n import _


class AuthException(Exception):
    def __init__(self, redirect_url: str):
        self.redirect_url = redirect_url


def require_session_user(request: Request, db: Session = Depends(get_db)) -> Member:
    user_id = request.session.get("user_id")
    if not user_id:
        raise AuthException("/login")
    user = db.get(Member, user_id)
    if not user or user.is_removed:
        request.session.clear()
        raise AuthException("/login")
    return user


def require_user(user: Member = Depends(require_session_user)) -> Member:
    if user.force_password_change:
        raise AuthException("/change-password")
    return user


def require_admin(user: Member = Depends(require_user)) -> Member:
    if not user.is_admin:
        raise AuthException("/today")
    return user


def require_mutable_admin(request: Request, user: Member = Depends(require_admin)) -> Member:
    if user.is_sentinel:
        request.session.setdefault("_flashes", []).append(
            {"message": _("Sentinel accounts are read-only."), "category": "error"}
        )
        raise AuthException("/admin")
    return user
