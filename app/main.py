import os
import bcrypt
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import text, inspect as sa_inspect
from sqlalchemy.orm import Session

from .database import engine, SessionLocal, Base
from .models import Member, Chore, ChoreState
from .dependencies import AuthException
from .routers import auth as auth_router
from .routers import chores as chores_router
from .routers import admin as admin_router
from .routers import account as account_router
from . import i18n as i18n_module
from .i18n import set_language, reset_language

BASE_DIR = Path(__file__).resolve().parent.parent

DEFAULT_CHORES = [
    {"name": "Sweep room", "icon": "🧹", "limit_hours": 48},
    {"name": "Take out trash", "icon": "🗑️", "limit_hours": 36},
    {"name": "Refill water", "icon": "💧", "limit_hours": 72},
    {"name": "Clean bathroom", "icon": "🚿", "limit_hours": 240},
    {"name": "Clean toilet", "icon": "🚽", "limit_hours": 168},
]


def _migrate():
    cols = [c["name"] for c in sa_inspect(engine).get_columns("members")]
    with engine.begin() as conn:
        if "is_sentinel" not in cols:
            conn.execute(text("ALTER TABLE members ADD COLUMN is_sentinel BOOLEAN NOT NULL DEFAULT 0"))
        if "language" not in cols:
            conn.execute(text("ALTER TABLE members ADD COLUMN language VARCHAR NOT NULL DEFAULT 'en'"))
        if "tiebreak_order" not in cols:
            conn.execute(text("ALTER TABLE members ADD COLUMN tiebreak_order INTEGER NOT NULL DEFAULT 0"))
    chore_cols = [c["name"] for c in sa_inspect(engine).get_columns("chores")]
    with engine.begin() as conn:
        if "name_vi" not in chore_cols:
            conn.execute(text("ALTER TABLE chores ADD COLUMN name_vi VARCHAR"))
        if "notes" not in chore_cols:
            conn.execute(text("ALTER TABLE chores ADD COLUMN notes TEXT"))


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate()
    db: Session = SessionLocal()
    try:
        admin = db.query(Member).filter(Member.username == "admin").first()
        if not admin:
            hashed = bcrypt.hashpw(b"admin", bcrypt.gensalt()).decode()
            admin = Member(
                username="admin",
                password=hashed,
                display_name="Admin",
                is_admin=True,
                is_active=True,
                force_password_change=True,
                joined_at=datetime.utcnow(),
            )
            db.add(admin)
            db.flush()

            for cd in DEFAULT_CHORES:
                chore = Chore(**cd)
                db.add(chore)
                db.flush()
                db.add(ChoreState(member_id=admin.id, chore_id=chore.id, tally=0, deficit=0))

            db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan, title="Dorm Chore Manager")


@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    lang = request.session.get("lang", "en")
    tokens = set_language(lang)
    try:
        response = await call_next(request)
    finally:
        reset_language(tokens)
    return response


SECRET_KEY = os.getenv("SECRET_KEY", "change-me-please-set-SECRET_KEY-env-var")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    session_cookie="dorm_session",
    same_site="lax",
    https_only=False,
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _time_ago(dt: datetime) -> str:
    _ = i18n_module._
    if dt is None:
        return _("never done")
    diff = datetime.utcnow() - dt
    secs = diff.total_seconds()
    if secs < 60:
        return _("just now")
    if secs < 3600:
        return _("%(n)sm ago") % {"n": int(secs / 60)}
    if secs < 86400:
        return _("%(n)sh ago") % {"n": int(secs / 3600)}
    return _("%(n)sd ago") % {"n": int(secs / 86400)}


def _fmt_hours(hours: float) -> str:
    if hours == float("inf"):
        return "∞"
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 48:
        return f"{hours:.0f}h"
    return f"{hours/24:.0f}d"


def _chore_name(chore) -> str:
    if chore is None:
        return ""
    if i18n_module.get_lang() == "vi" and chore.name_vi:
        return chore.name_vi
    return chore.name


templates.env.filters["time_ago"] = _time_ago
templates.env.filters["fmt_hours"] = _fmt_hours
templates.env.globals["_"] = i18n_module._
templates.env.globals["ngettext"] = i18n_module.ngettext
templates.env.globals["current_lang"] = i18n_module.get_lang
templates.env.globals["SUPPORTED_LANGUAGES"] = i18n_module.SUPPORTED
templates.env.globals["chore_name"] = _chore_name


@app.exception_handler(AuthException)
async def auth_exception_handler(request: Request, exc: AuthException):
    return RedirectResponse(url=exc.redirect_url, status_code=302)


auth_router.set_templates(templates)
chores_router.set_templates(templates)
admin_router.set_templates(templates)
account_router.set_templates(templates)

app.include_router(auth_router.router)
app.include_router(chores_router.router)
app.include_router(admin_router.router)
app.include_router(account_router.router)


@app.get("/")
async def root():
    return RedirectResponse(url="/today", status_code=302)
