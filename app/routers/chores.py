from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_user
from ..models import Member, Chore, ChoreLog
from ..logic import apply_chore_log, build_chore_card, get_recommendation, is_done_today

router = APIRouter()
templates: Jinja2Templates = None


def set_templates(t: Jinja2Templates):
    global templates
    templates = t


def flash(request: Request, message: str, category: str = "info"):
    request.session.setdefault("_flashes", []).append({"message": message, "category": category})


def get_flashes(request: Request):
    return request.session.pop("_flashes", [])


def _build_today_context(db: Session, user: Member):
    active_chores = db.query(Chore).filter(Chore.is_active == True).all()
    cards = [build_chore_card(db, chore, user) for chore in active_chores]

    urgent = sorted(
        [c for c in cards if c["is_urgent"]],
        key=lambda x: x["overdue_by"],
        reverse=True,
    )
    routine = [c for c in cards if not c["is_urgent"]]

    pending_count = sum(
        1 for c in cards
        if c["is_recommended_me"] and not c["done_today"]
    )

    my_pending = [c for c in cards if c["is_recommended_me"] and not c["done_today"]]
    my_rec_urgent = sorted(
        [c for c in my_pending if c["is_urgent"]],
        key=lambda x: x["overdue_by"],
        reverse=True,
    )
    my_rec_routine = [c for c in my_pending if not c["is_urgent"]]
    other_chores = [c for c in cards if not c["is_recommended_me"]]

    return {
        "urgent": urgent,
        "routine": routine,
        "pending_count": pending_count,
        "my_rec_urgent": my_rec_urgent,
        "my_rec_routine": my_rec_routine,
        "other_chores": other_chores,
    }


@router.get("/today")
async def today_page(
    request: Request,
    user: Member = Depends(require_user),
    db: Session = Depends(get_db),
):
    ctx = _build_today_context(db, user)
    return templates.TemplateResponse(
        request, "today.html", {"user": user, "flashes": get_flashes(request), **ctx}
    )


@router.post("/chores/log")
async def log_chore(
    request: Request,
    chore_id: int = Form(...),
    user: Member = Depends(require_user),
    db: Session = Depends(get_db),
):
    chore = db.get(Chore, chore_id)
    if not chore or not chore.is_active:
        flash(request, "Chore not found.", "error")
        return RedirectResponse(url="/today", status_code=302)

    apply_chore_log(db, user, chore)
    db.commit()
    flash(request, f"{chore.icon} {chore.name} logged!", "success")
    return RedirectResponse(url="/today", status_code=302)


@router.post("/chores/log-all")
async def log_all_recommended(
    request: Request,
    user: Member = Depends(require_user),
    db: Session = Depends(get_db),
):
    active_chores = db.query(Chore).filter(Chore.is_active == True).all()
    count = 0
    for chore in active_chores:
        recommended = get_recommendation(db, chore)
        if recommended and recommended.id == user.id and not is_done_today(db, chore.id):
            apply_chore_log(db, user, chore)
            count += 1
    db.commit()
    if count:
        flash(request, f"Logged {count} recommended chore(s)!", "success")
    else:
        flash(request, "No pending recommended chores.", "info")
    return RedirectResponse(url="/today", status_code=302)


@router.get("/tally")
async def tally_page(
    request: Request,
    user: Member = Depends(require_user),
    db: Session = Depends(get_db),
):
    members = (
        db.query(Member)
        .filter(Member.is_removed == False, Member.is_admin == False)
        .order_by(Member.joined_at)
        .all()
    )
    chores = db.query(Chore).filter(Chore.is_active == True).all()

    matrix = {}
    totals = {}
    for member in members:
        matrix[member.id] = {}
        totals[member.id] = 0
        for chore in chores:
            from ..models import ChoreState
            state = db.get(ChoreState, (member.id, chore.id))
            tally = state.tally if state else 0
            matrix[member.id][chore.id] = tally
            totals[member.id] += tally

    chore_totals = {
        chore.id: sum(matrix[m.id][chore.id] for m in members)
        for chore in chores
    }

    return templates.TemplateResponse(
        request, "tally.html", {
            "user": user,
            "flashes": get_flashes(request),
            "members": members,
            "chores": chores,
            "matrix": matrix,
            "totals": totals,
            "chore_totals": chore_totals,
        }
    )


@router.get("/history")
async def history_page(
    request: Request,
    page: int = 1,
    mode: str = "list",
    year: int = 0,
    month: int = 0,
    user: Member = Depends(require_user),
    db: Session = Depends(get_db),
):
    import calendar
    from datetime import datetime

    if mode == "calendar":
        now = datetime.utcnow()
        y = year or now.year
        m = month or now.month

        first_day = datetime(y, m, 1)
        _, last_day_num = calendar.monthrange(y, m)
        last_day = datetime(y, m, last_day_num, 23, 59, 59)

        cal_logs = (
            db.query(ChoreLog)
            .filter(ChoreLog.logged_at >= first_day, ChoreLog.logged_at <= last_day)
            .order_by(ChoreLog.logged_at)
            .all()
        )

        logs_by_day: dict = {}
        for log in cal_logs:
            d = log.logged_at.day
            logs_by_day.setdefault(d, []).append(log)

        prev_m = m - 1 or 12
        prev_y = y if m > 1 else y - 1
        next_m = m % 12 + 1
        next_y = y if m < 12 else y + 1

        return templates.TemplateResponse(
            request, "history.html", {
                "user": user,
                "flashes": get_flashes(request),
                "mode": "calendar",
                "year": y,
                "month": m,
                "month_name": first_day.strftime("%B %Y"),
                "calendar_weeks": calendar.monthcalendar(y, m),
                "logs_by_day": logs_by_day,
                "prev_year": prev_y,
                "prev_month": prev_m,
                "next_year": next_y,
                "next_month": next_m,
                "today_day": now.day if now.year == y and now.month == m else -1,
            }
        )

    per_page = 30
    offset = (page - 1) * per_page
    total = db.query(ChoreLog).count()
    logs = (
        db.query(ChoreLog)
        .order_by(ChoreLog.logged_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    total_pages = max(1, (total + per_page - 1) // per_page)

    return templates.TemplateResponse(
        request, "history.html", {
            "user": user,
            "flashes": get_flashes(request),
            "mode": "list",
            "logs": logs,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        }
    )
