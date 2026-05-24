import re
from pathlib import Path
from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import RedirectResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db, AVATAR_DIR
from ..dependencies import require_user, require_session_user
from ..models import Member

router = APIRouter()
templates: Jinja2Templates = None


def set_templates(t: Jinja2Templates):
    global templates
    templates = t


def flash(request: Request, message: str, category: str = "info"):
    request.session.setdefault("_flashes", []).append({"message": message, "category": category})


def get_flashes(request: Request):
    return request.session.pop("_flashes", [])


_AVATAR_COLORS = [
    "#6366f1", "#ec4899", "#14b8a6", "#f59e0b",
    "#10b981", "#8b5cf6", "#ef4444", "#3b82f6",
]


def _svg_avatar(member: Member) -> str:
    color = _AVATAR_COLORS[member.id % len(_AVATAR_COLORS)]
    initial = member.display_name[0].upper()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        f'<circle cx="32" cy="32" r="32" fill="{color}"/>'
        '<text x="32" y="32" text-anchor="middle" dominant-baseline="central" '
        f'fill="white" font-size="28" font-family="system-ui,sans-serif" font-weight="bold">{initial}</text>'
        '</svg>'
    )


def _find_avatar(member_id: int) -> Path | None:
    for ext in ("jpg", "jpeg", "png", "webp", "gif"):
        p = AVATAR_DIR / f"{member_id}.{ext}"
        if p.exists():
            return p
    return None


# ── Avatar serving ───────────────────────────────────────

@router.get("/avatar/{member_id}")
async def serve_avatar(member_id: int, db: Session = Depends(get_db)):
    path = _find_avatar(member_id)
    if path:
        return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})
    member = db.get(Member, member_id)
    if not member:
        return Response(status_code=404)
    return Response(
        content=_svg_avatar(member),
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-cache"},
    )


# ── Account page ─────────────────────────────────────────

@router.get("/account")
async def account_page(request: Request, user: Member = Depends(require_user)):
    has_avatar = _find_avatar(user.id) is not None
    return templates.TemplateResponse(
        request, "account.html", {
            "user": user,
            "flashes": get_flashes(request),
            "has_avatar": has_avatar,
        }
    )


# ── Username change ──────────────────────────────────────

@router.post("/account/username")
async def change_username(
    request: Request,
    new_username: str = Form(...),
    user: Member = Depends(require_user),
    db: Session = Depends(get_db),
):
    new_username = new_username.strip().lower()
    if not re.match(r"^[a-z0-9_]{1,50}$", new_username):
        flash(request, "Username must be 1–50 lowercase letters, numbers, or underscores.", "error")
        return RedirectResponse(url="/account", status_code=302)
    if new_username == user.username:
        flash(request, "That's already your username.", "info")
        return RedirectResponse(url="/account", status_code=302)
    if db.query(Member).filter(Member.username == new_username).first():
        flash(request, f"'{new_username}' is already taken.", "error")
        return RedirectResponse(url="/account", status_code=302)
    user.username = new_username
    db.commit()
    flash(request, "Username updated.", "success")
    return RedirectResponse(url="/account", status_code=302)


# ── Avatar upload ────────────────────────────────────────

@router.post("/account/avatar")
async def upload_avatar(
    request: Request,
    avatar: UploadFile = File(...),
    user: Member = Depends(require_user),
):
    content_type = avatar.content_type or ""
    if not content_type.startswith("image/"):
        flash(request, "Please upload an image file.", "error")
        return RedirectResponse(url="/account", status_code=302)

    ext = content_type.split("/")[-1]
    if ext == "jpeg":
        ext = "jpg"
    if ext not in ("jpg", "png", "webp", "gif"):
        ext = "jpg"

    content = await avatar.read()
    if len(content) > 5 * 1024 * 1024:
        flash(request, "Image must be under 5 MB.", "error")
        return RedirectResponse(url="/account", status_code=302)

    for old_ext in ("jpg", "jpeg", "png", "webp", "gif"):
        old = AVATAR_DIR / f"{user.id}.{old_ext}"
        if old.exists():
            old.unlink()

    (AVATAR_DIR / f"{user.id}.{ext}").write_bytes(content)
    flash(request, "Profile picture updated.", "success")
    return RedirectResponse(url="/account", status_code=302)


@router.post("/account/avatar/remove")
async def remove_avatar(request: Request, user: Member = Depends(require_user)):
    removed = False
    for ext in ("jpg", "jpeg", "png", "webp", "gif"):
        p = AVATAR_DIR / f"{user.id}.{ext}"
        if p.exists():
            p.unlink()
            removed = True
    flash(request, "Profile picture removed." if removed else "No picture to remove.", "info")
    return RedirectResponse(url="/account", status_code=302)
