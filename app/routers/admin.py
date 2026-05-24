import bcrypt
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_admin, require_mutable_admin
from ..models import Member, Chore, ChoreState
from ..logic import apply_chore_log
from ..i18n import _

router = APIRouter(prefix="/admin")
templates: Jinja2Templates = None


def set_templates(t: Jinja2Templates):
    global templates
    templates = t


def flash(request: Request, message: str, category: str = "info"):
    request.session.setdefault("_flashes", []).append({"message": message, "category": category})


def get_flashes(request: Request):
    return request.session.pop("_flashes", [])


@router.get("")
async def admin_page(
    request: Request,
    user: Member = Depends(require_admin),
    db: Session = Depends(get_db),
):
    members = db.query(Member).filter(Member.is_removed == False).order_by(Member.joined_at).all()
    chores = db.query(Chore).order_by(Chore.id).all()
    active_members = [m for m in members if not m.is_removed]
    active_chores = [c for c in chores if c.is_active]
    return templates.TemplateResponse(
        request, "admin.html", {
            "user": user,
            "flashes": get_flashes(request),
            "members": members,
            "chores": chores,
            "active_members": active_members,
            "active_chores": active_chores,
        }
    )


# --- Member management ---

@router.post("/members")
async def add_member(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    existing = db.query(Member).filter(Member.username == username).first()
    if existing:
        flash(request, _("Username '%(username)s' is already taken.") % {"username": username}, "error")
        return RedirectResponse(url="/admin", status_code=302)

    from datetime import datetime
    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    new_member = Member(
        username=username,
        display_name=display_name,
        password=hashed,
        is_admin=False,
        is_active=True,
        force_password_change=True,
        joined_at=datetime.utcnow(),
    )
    db.add(new_member)
    db.flush()

    active_chores = db.query(Chore).filter(Chore.is_active == True).all()
    for chore in active_chores:
        state = ChoreState(member_id=new_member.id, chore_id=chore.id, tally=0, deficit=0)
        db.add(state)

    db.commit()
    flash(request, _("Member '%(name)s' added.") % {"name": display_name}, "success")
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/members/{member_id}/toggle-active")
async def toggle_member_active(
    request: Request,
    member_id: int,
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id)
    if not member or member.is_removed:
        flash(request, _("Member not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    if member.id == user.id:
        flash(request, _("You cannot deactivate yourself."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    member.is_active = not member.is_active
    db.commit()
    if member.is_active:
        flash(request, _("'%(name)s' activated.") % {"name": member.display_name}, "success")
    else:
        flash(request, _("'%(name)s' deactivated.") % {"name": member.display_name}, "success")
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/members/{member_id}/reset-password")
async def reset_member_password(
    request: Request,
    member_id: int,
    new_password: str = Form(...),
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id)
    if not member or member.is_removed:
        flash(request, _("Member not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    if len(new_password) < 6:
        flash(request, _("Password must be at least 6 characters."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    member.password = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    member.force_password_change = True
    db.commit()
    flash(request, _("Password for '%(name)s' reset. They must change it on next login.") % {"name": member.display_name}, "success")
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/members/{member_id}/remove")
async def remove_member(
    request: Request,
    member_id: int,
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id)
    if not member or member.is_removed:
        flash(request, _("Member not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    if member.id == user.id:
        flash(request, _("You cannot remove yourself."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    member.is_removed = True
    member.is_active = False
    db.commit()
    flash(request, _("'%(name)s' removed. Logs preserved.") % {"name": member.display_name}, "success")
    return RedirectResponse(url="/admin", status_code=302)


# --- Chore management ---

@router.post("/chores")
async def add_chore(
    request: Request,
    name: str = Form(...),
    name_vi: str = Form(""),
    icon: str = Form("🧹"),
    limit_hours: int = Form(...),
    notes: str = Form(""),
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    chore = Chore(name=name, name_vi=name_vi or None, icon=icon or "🧹", limit_hours=limit_hours, notes=notes or None, is_active=True)
    db.add(chore)
    db.flush()

    active_members = (
        db.query(Member).filter(Member.is_active == True, Member.is_removed == False).all()
    )
    for member in active_members:
        state = ChoreState(member_id=member.id, chore_id=chore.id, tally=0, deficit=0)
        db.add(state)

    db.commit()
    flash(request, _("Chore '%(name)s' added.") % {"name": name}, "success")
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/chores/{chore_id}/edit")
async def edit_chore(
    request: Request,
    chore_id: int,
    name: str = Form(...),
    name_vi: str = Form(""),
    icon: str = Form("🧹"),
    limit_hours: int = Form(...),
    notes: str = Form(""),
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    chore = db.get(Chore, chore_id)
    if not chore:
        flash(request, _("Chore not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    chore.name = name
    chore.name_vi = name_vi or None
    chore.icon = icon or "🧹"
    chore.limit_hours = limit_hours
    chore.notes = notes or None
    db.commit()
    flash(request, _("Chore '%(name)s' updated.") % {"name": name}, "success")
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/chores/{chore_id}/toggle")
async def toggle_chore(
    request: Request,
    chore_id: int,
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    chore = db.get(Chore, chore_id)
    if not chore:
        flash(request, _("Chore not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    chore.is_active = not chore.is_active
    db.commit()
    if chore.is_active:
        flash(request, _("Chore '%(name)s' activated.") % {"name": chore.name}, "success")
    else:
        flash(request, _("Chore '%(name)s' deactivated.") % {"name": chore.name}, "success")
    return RedirectResponse(url="/admin", status_code=302)


# --- Override logging ---

@router.post("/log-on-behalf")
async def log_on_behalf(
    request: Request,
    member_id: int = Form(...),
    chore_id: int = Form(...),
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id)
    chore = db.get(Chore, chore_id)
    if not member or member.is_removed:
        flash(request, _("Member not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    if not chore or not chore.is_active:
        flash(request, _("Chore not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)

    apply_chore_log(db, member, chore)
    db.commit()
    flash(
        request,
        _("Logged '%(chore)s' on behalf of %(member)s.") % {"chore": chore.name, "member": member.display_name},
        "success",
    )
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/members/{member_id}/toggle-sentinel")
async def toggle_sentinel(
    request: Request,
    member_id: int,
    user: Member = Depends(require_mutable_admin),
    db: Session = Depends(get_db),
):
    member = db.get(Member, member_id)
    if not member or member.is_removed:
        flash(request, _("Member not found."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    if not member.is_admin:
        flash(request, _("Sentinel role requires admin access."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    if member.id == user.id:
        flash(request, _("You cannot change your own sentinel status."), "error")
        return RedirectResponse(url="/admin", status_code=302)
    member.is_sentinel = not member.is_sentinel
    db.commit()
    if member.is_sentinel:
        flash(request, _("'%(name)s' marked as sentinel.") % {"name": member.display_name}, "success")
    else:
        flash(request, _("'%(name)s' no longer sentinel.") % {"name": member.display_name}, "success")
    return RedirectResponse(url="/admin", status_code=302)
