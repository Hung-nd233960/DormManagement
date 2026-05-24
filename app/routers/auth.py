import bcrypt
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_session_user
from ..models import Member

router = APIRouter()
templates: Jinja2Templates = None  # set in main.py


def set_templates(t: Jinja2Templates):
    global templates
    templates = t


def flash(request: Request, message: str, category: str = "info"):
    request.session.setdefault("_flashes", []).append({"message": message, "category": category})


def get_flashes(request: Request):
    return request.session.pop("_flashes", [])


@router.get("/login")
async def login_page(request: Request):
    user_id = request.session.get("user_id")
    if user_id:
        return RedirectResponse(url="/today", status_code=302)
    return templates.TemplateResponse(
        request, "login.html", {"flashes": get_flashes(request)}
    )


@router.post("/auth/login")
async def do_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    member = (
        db.query(Member).filter(Member.username == username, Member.is_removed == False).first()
    )
    if not member or not bcrypt.checkpw(password.encode(), member.password.encode()):
        flash(request, "Invalid username or password.", "error")
        return RedirectResponse(url="/login", status_code=302)

    request.session["user_id"] = member.id
    if member.force_password_change:
        return RedirectResponse(url="/change-password", status_code=302)
    return RedirectResponse(url="/today", status_code=302)


@router.post("/auth/logout")
async def do_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@router.get("/change-password")
async def change_password_page(request: Request, user: Member = Depends(require_session_user)):
    return templates.TemplateResponse(
        request, "change_password.html", {"user": user, "flashes": get_flashes(request)}
    )


@router.post("/auth/toggle-active")
async def toggle_own_active(
    request: Request,
    user: Member = Depends(require_session_user),
    db: Session = Depends(get_db),
):
    user.is_active = not user.is_active
    db.commit()
    status = "active" if user.is_active else "inactive"
    flash(request, f"You are now marked as {status}.", "info")
    return RedirectResponse(url="/today", status_code=302)


@router.post("/auth/change-password")
async def do_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: Member = Depends(require_session_user),
    db: Session = Depends(get_db),
):
    if not bcrypt.checkpw(current_password.encode(), user.password.encode()):
        flash(request, "Current password is incorrect.", "error")
        return RedirectResponse(url="/change-password", status_code=302)
    if new_password != confirm_password:
        flash(request, "New passwords do not match.", "error")
        return RedirectResponse(url="/change-password", status_code=302)
    if len(new_password) < 6:
        flash(request, "Password must be at least 6 characters.", "error")
        return RedirectResponse(url="/change-password", status_code=302)

    user.password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    user.force_password_change = False
    db.commit()
    flash(request, "Password changed successfully.", "success")
    return RedirectResponse(url="/today", status_code=302)
