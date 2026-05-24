from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from .models import Member, Chore, ChoreState, ChoreLog


def get_or_create_state(db: Session, member_id: int, chore_id: int) -> ChoreState:
    state = db.get(ChoreState, (member_id, chore_id))
    if not state:
        state = ChoreState(member_id=member_id, chore_id=chore_id, tally=0, deficit=0)
        db.add(state)
        db.flush()
    return state


def apply_chore_log(db: Session, member: Member, chore: Chore, note: str = None):
    log_entry = ChoreLog(
        member_id=member.id,
        chore_id=chore.id,
        logged_at=datetime.utcnow(),
        note=note,
        logged_member_name=member.display_name,
        logged_chore_name=chore.name,
    )
    db.add(log_entry)

    if member.is_admin:
        return

    state = get_or_create_state(db, member.id, chore.id)
    state.tally += 1

    if state.deficit == 0:
        active_others = (
            db.query(Member)
            .filter(
                Member.is_active == True,
                Member.is_removed == False,
                Member.is_admin == False,
                Member.id != member.id,
            )
            .all()
        )
        for other in active_others:
            other_state = get_or_create_state(db, other.id, chore.id)
            other_state.deficit += 1
    else:
        state.deficit -= 1


def get_recommendation(db: Session, chore: Chore) -> Optional[Member]:
    active_members = (
        db.query(Member)
        .filter(Member.is_active == True, Member.is_removed == False, Member.is_admin == False)
        .all()
    )
    if not active_members:
        return None

    max_deficit = -1
    best = []
    for member in active_members:
        state = db.get(ChoreState, (member.id, chore.id))
        deficit = state.deficit if state else 0
        if deficit > max_deficit:
            max_deficit = deficit
            best = [member]
        elif deficit == max_deficit:
            best.append(member)

    # Tiebreak: explicit rank first (1 = highest), unranked (0) sorted last, then stable by id.
    return min(best, key=lambda m: (m.tiebreak_order if m.tiebreak_order > 0 else float("inf"), m.id))


def get_chore_urgency(db: Session, chore: Chore):
    last_log = (
        db.query(ChoreLog)
        .filter(ChoreLog.chore_id == chore.id)
        .order_by(ChoreLog.logged_at.desc())
        .first()
    )
    now = datetime.utcnow()
    if last_log is None:
        hours_since = float("inf")
        last_done = None
    else:
        hours_since = (now - last_log.logged_at).total_seconds() / 3600
        last_done = last_log.logged_at

    is_urgent = hours_since >= chore.limit_hours
    overdue_by = hours_since - chore.limit_hours if is_urgent and hours_since != float("inf") else 0

    return {
        "hours_since": hours_since,
        "last_done": last_done,
        "is_urgent": is_urgent,
        "overdue_by": overdue_by,
    }


def is_done_today(db: Session, chore_id: int) -> bool:
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    return (
        db.query(ChoreLog)
        .filter(ChoreLog.chore_id == chore_id, ChoreLog.logged_at >= today_start)
        .first()
        is not None
    )


def build_chore_card(db: Session, chore: Chore, user: Member) -> dict:
    urgency = get_chore_urgency(db, chore)
    recommended = get_recommendation(db, chore)
    done_today = is_done_today(db, chore.id)
    return {
        "chore": chore,
        "is_urgent": urgency["is_urgent"],
        "overdue_by": urgency["overdue_by"],
        "hours_since": urgency["hours_since"],
        "last_done": urgency["last_done"],
        "done_today": done_today,
        "recommended": recommended,
        "is_recommended_me": recommended is not None and recommended.id == user.id,
    }
