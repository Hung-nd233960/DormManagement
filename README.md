# DormChores

A lightweight chore-tracking web app for shared living spaces. Runs entirely on your local network — no cloud accounts, no external services.

## Features

- **Today view** — see which chores are overdue or due soon, with smart recommendations on who should do what next based on deficit tracking
- **Tally** — lifetime chore counts per member, with per-chore contribution bars
- **History** — paginated log and monthly calendar view of who did what and when
- **Admin panel** — manage members and chores, log chores on behalf of others
- **Account page** — profile picture upload, username change, password change, active/inactive toggle
- **Sentinel role** — admin-level read access for IoT devices or automation scripts, no write permissions
- **Dark / light mode** — persisted per browser via `localStorage`
- **Mobile-optimised** — bottom tab bar, responsive tally table, touch-friendly modals

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12 · FastAPI · SQLAlchemy · SQLite |
| Templating | Jinja2 · Alpine.js (vendored) |
| Styling | Vanilla CSS with custom properties |
| Auth | Starlette session middleware · bcrypt |
| Deployment | Docker · Docker Compose |

## Quick start (Docker)

**1. Clone and enter the repo**

```bash
git clone https://github.com/your-username/DormManagement.git
cd DormManagement
```

**2. Create your `.env` file**

```bash
cp example.env .env
```

Open `.env` and set a real `SECRET_KEY`:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Paste the output as the value of `SECRET_KEY`.

**3. Build and run**

```bash
docker compose up -d --build
```

The app is now available at **http://localhost:8000** (or replace `localhost` with your machine's LAN IP for other devices on the network).

**4. Log in**

| Field | Value |
|---|---|
| Username | `admin` |
| Password | `admin` |

You will be forced to change the password on first login.

## Manual setup (without Docker)

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp example.env .env          # edit SECRET_KEY
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | Yes | `change-me-…` | Signs session cookies. Use a random 32-byte hex string. |
| `DB_PATH` | No | `./data/dorm.db` | Path to the SQLite database file. |

## Data persistence

All persistent data lives in the `data/` directory:

```
data/
├── dorm.db        # SQLite database
└── avatars/       # uploaded profile pictures
```

When using Docker Compose this directory is bind-mounted from the host (`./data:/app/data`), so your data survives container rebuilds.

> `data/` is excluded from git. Only `data/.gitkeep` is committed to preserve the directory structure.

## Project structure

```
.
├── app/
│   ├── main.py          # FastAPI app, startup, Jinja2 filters
│   ├── models.py        # SQLAlchemy models (Member, Chore, ChoreState, ChoreLog)
│   ├── database.py      # Engine, session, avatar directory
│   ├── dependencies.py  # Auth dependencies (require_user, require_admin, require_mutable_admin)
│   ├── logic.py         # Chore log application, deficit calculation, recommendations
│   └── routers/
│       ├── auth.py      # Login, logout, password change, active toggle
│       ├── chores.py    # Today, Tally, History pages
│       ├── admin.py     # Admin panel (member & chore management)
│       └── account.py   # Account page, avatar upload, username change
├── templates/           # Jinja2 HTML templates
├── static/
│   ├── css/style.css
│   └── js/alpine.min.js
├── data/                # Runtime data (gitignored)
├── Dockerfile
├── docker-compose.yml
├── example.env
└── requirements.txt
```

## Roles

| Role | Description |
|---|---|
| Regular member | Can log their own chores, manage their own account |
| Admin | Full access to Admin panel (add/remove members and chores, log on behalf) |
| Sentinel | Admin-level read access only — write actions are blocked. Intended for IoT integrations. |

## How the deficit system works

Each member starts with a deficit of 0 for every chore. When a chore is logged:

- The member who did it gains +1 tally and has their deficit reset toward 0.
- All other active members accumulate deficit proportionally over time.

The **recommendation** on the Today page surfaces the active member with the highest deficit for each chore, so work stays evenly distributed without manual coordination.

Admins are excluded from all deficit tracking and recommendations.
