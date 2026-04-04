# AGENTS.md

## Project Context

Recon is the backend for a 3-day, 600-person DEFCON-style cybersecurity fest (Apr 19-21, VIT-AP). It powers the participant-facing PWA, admin ops dashboard, and sponsor/partner dashboards. The backend is a FastAPI application with PostgreSQL (Neon), Redis, and Logfire observability.

**External systems (do NOT rebuild):**
- **Luma** handles registration, RSVP, and ticket scanning. Participants who pass selection are directed to sign up on our platform.
- **CTFd** (self-hosted on AWS EC2) handles the CTF competition platform.
- **KOTH** runs on local VLAN-segmented infrastructure (not cloud).
- **n8n** handles form automation (Google Forms -> webhook -> our DB).
- **Grafana/CloudWatch** handles infrastructure monitoring.
- **Telegram/WhatsApp** handles volunteer comms and escalation channels.

**What this backend DOES own:**
- Participant PWA backend: schedule, zone map, queue indicators, passport points, leaderboard, push notifications, check-in state.
- NFC Lock Hunt system: `/tap`, `/solve`, `/progress`, `/final` endpoints with team state machine and NFC token verification.
- Points/passport economy: all point mutations across zones and events.
- Zone management: capacity tracking, queue position, status (red/amber/green).
- Incident logging: webhook ingestion from n8n/Google Forms.
- Admin dashboard: aggregated ops view, overrides, role checks.
- Sponsor/partner dashboard: post-event ROI metrics, footfall, engagement data.

---

## Commit Rules

- **NEVER** add "Co-Authored-By" lines or any co-author attribution in commits. Do not mention co-authorship in any capacity.

---

## Tech Stack

- **Framework:** FastAPI (async)
- **ORM / Validation:** SQLModel (SQLAlchemy + Pydantic combined)
- **Database:** PostgreSQL via asyncpg (Neon managed, serverless)
- **Cache / Messaging:** Redis (`redis.asyncio`)
- **Observability:** Logfire (auto-instrumented for FastAPI, asyncpg, Redis)
- **Auth:** Stateless JWT access tokens (60min) + stateful refresh tokens (7 days) in httpOnly cookies. OAuth via Authlib (Google).
- **Config:** Pydantic Settings (`app/core/config.py`)
- **Migrations:** Alembic (async, autodiscovery from `app/models/__init__.py`)
- **File Storage:** Cloudflare R2 (S3-compatible) with presigned URLs

---

## Architecture

### Pattern: Router -> Controller -> Service -> CRUD

```
Router (thin HTTP layer)  ->  Controller (orchestration + parsing)  ->  Service (business logic)  ->  CRUD (DB queries)
```

- **Routers** (`router.py`): Parse HTTP request, pull dependencies via `Depends()`, return response. NO business logic. No direct DB queries.
- **Controllers** (`controller.py`): Orchestration layer. Handles any pre/post-processing, payload transformation, or multi-service coordination that doesn't belong in the HTTP layer or business logic. May call multiple services. No HTTP context (`Request`/`Response`).
- **Services** (`service.py`): Pure business logic for a single concern. No HTTP context. Receives typed data, returns domain objects or raises `HTTPException`.
- **CRUD** (`crud.py`): Raw database operations only. SELECT, INSERT, UPDATE, DELETE. No business decisions.

### Current State (Migration In Progress)

The codebase has two structures coexisting:

1. **Old horizontal layers** (`app/models/`, `app/schemas/`, `app/crud/`, `app/services/`, `app/controllers/`): Auth, users, R2 uploads live here. This is the reference implementation.
2. **New domain slices** (`app/domains/`): Scaffolded but empty. All new features go here.

New domains use `router.py -> controller.py -> service.py -> crud.py` inside their domain folder.

### Directory Structure

```
backend/app/
  main.py                       # Lifespan, middleware, app mounts
  core/                         # Config, security, OAuth — do not restructure
    config.py
    security.py
    oauth.py
  db/
    database.py
  models/
    __init__.py                 # Alembic aggregator — import all domain models here
  shared/                       # Cross-domain utilities
    deps/                       # FastAPI Depends() — get_db, get_redis, get_current_user, require_roles
    rbac/                       # Startup role seeding and admin bootstrap
    exceptions/                 # Shared HTTP exception classes
    storage/                    # R2/S3 client and presigned URL logic
      validators/               # File type/extension/key validation
    models/
      base.py                   # Base SQLModel (id, created_at, updated_at)
  domains/                      # All business features as vertical slices
    auth/                       # COMPLETE — OAuth, JWT, user CRUD
      models/                   # user.py, role.py, oauth_account.py, refresh_token.py
      schemas/                  # UserRead, UserCreate, UserUpdate, UserProfile, RoleRead
      crud/                     # All DB operations for auth models
      service/                  # Business logic (OAuth flow, token management, user management)
      controller/               # Orchestration layer
      router/                   # /auth/* and /users/* routes
      tests/
    participants/               # SCAFFOLD ONLY
    zones/                      # SCAFFOLD ONLY
    points/                     # SCAFFOLD ONLY
    shop/                       # SCAFFOLD ONLY
    schedule/                   # SCAFFOLD ONLY
    announcements/              # SCAFFOLD ONLY
    teams/                      # SCAFFOLD ONLY
    incidents/                  # SCAFFOLD ONLY
    webhooks/                   # SCAFFOLD ONLY (no models/, no crud/)
    admin/                      # SCAFFOLD ONLY (no models/, no crud/)
  api/
    v1/
      api.py                    # Mounts domain routers — one include_router per domain
      routers/
        r2.py                   # Infrastructure router — R2 presigned URLs
```

### Adding a New Domain

1. Create folder under `domains/<name>/` with: `__init__.py`, `router.py`, `controller.py`, `service.py`, `crud.py`, `models.py`, `schemas.py`
2. Add model imports to `app/models/__init__.py` so Alembic discovers them
3. Add one `include_router()` line in `api/v1/api.py`
4. Write tests in `domains/<name>/tests/`
5. Update the **Project State** section in this file to reflect what was added

A contributor owns their entire domain folder end-to-end. Cross-domain touches are limited to steps 2, 3, and 5.

---

## Base Model

All database models inherit from `app.models.base.Base` which provides:
- `id`: UUID primary key (auto-generated)
- `created_at`: timezone-aware datetime with server default
- `updated_at`: timezone-aware datetime with onupdate trigger

```python
from app.models.base import Base

class Zone(Base, ZoneBase, table=True):
    __tablename__ = "zones"
    # domain-specific fields here
```

---

## Dependency Injection

Never import raw Redis or Session clients in business logic. Always use `Depends()`:

```python
from app.api.deps import get_db, get_redis, get_current_user, require_roles

@router.get("/zones")
async def list_zones(db: AsyncSession = Depends(get_db)):
    ...

@router.post("/zones/{id}/override")
async def override_zone(user: User = Depends(require_roles("admin", "ops_chief"))):
    ...
```

### Roles

Defined in `app/models/role.py`. Current roles: `admin`, `participant`, `partner`. Default role assigned to all new users is `participant`. Use `require_roles()` from `api/deps.py` for route-level access control. Every route must declare its required role explicitly. The `applicant` role has been removed — registration and selection are handled externally by Luma.

---

## Points Economy Rule

All point mutations MUST go through the points domain service with a named reason code. No domain writes directly to the points table.

```python
await points_service.award(db, participant_id=pid, amount=50, reason="zone.nfc_lock_hunt.complete")
await points_service.award(db, participant_id=pid, amount=10, reason="zone.forensics_sprint.flag")
```

This gives a clean audit log and the leaderboard is always derivable from a single table.

---

## Observability

Logfire is auto-instrumented in `main.py` for FastAPI, asyncpg, and Redis. Do not add verbose `logging.info()` blocks. Use `logfire.span()` for meaningful business state context only:

```python
import logfire
with logfire.span("calculating_leaderboard"):
    result = await compute_leaderboard(db)
```

---

## Security Rules

- Never log or expose participant PII (emails, tokens, passwords) in responses or logs.
- All challenge/competition endpoints must be sandbox-aware.
- Access tokens are read from `access_token` httpOnly cookie, not headers.
- Refresh tokens use SHA-256 hashing in DB with theft detection (reuse = revoke all).
- Secrets and keys live in `.env` only. Never hardcode them.

---

## Database Conventions

- Use `SQLModel` with `table=True` for DB models. Use plain `SQLModel` (no `table=True`) for Pydantic schemas.
- All async: `AsyncSession`, `async def`, `await db.exec()`.
- Session lifecycle managed by `get_db()` dependency (auto-commit on success, rollback on exception).
- Foreign keys use UUID type matching the `Base.id` field.
- Migrations via Alembic: `cd backend && alembic revision --autogenerate -m "description"` then `alembic upgrade head`.

---

## Testing (For Contributors)

Pattern: HTTP in, assert the response. No direct DB manipulation in tests.

```python
async def test_zone_checkin_succeeds(client, seed_zone, seed_participant):
    response = await client.post(f"/zones/{seed_zone.id}/checkin", json={
        "participant_id": seed_participant.id
    })
    assert response.status_code == 200
    assert response.json()["status"] == "checked_in"
```

Rules:
1. One test file per router file
2. Test the happy path first, then the most obvious failure case
3. Never assert on IDs, assert on status codes and meaningful fields
4. If setup needs more than 3 things, it needs a fixture

---

## Project State (Agent-Maintained)

Agents MUST update this section after completing any meaningful change — domain additions, structural migrations, schema changes, or architectural decisions. This is the living state of the codebase. Do not leave it stale.

### Current Migration Status

- Vertical domain slice migration is complete for the auth domain. All old horizontal directories (`models/`, `schemas/`, `crud/`, `services/`, `controllers/`) have been deleted.
- `shared/` is populated: `deps/`, `rbac/`, `exceptions/`, `storage/`, `storage/validators/`, `models/base.py`.
- `domains/auth/` is fully migrated with `models/`, `schemas/`, `crud/`, `service/`, `controller/`, `router/`, `tests/` — all as packages.
- All other domain folders are scaffolded (empty `__init__.py` files only).
- `app/models/__init__.py` is the Alembic aggregator — import new domain models here when added.
- `api/v1/api.py` mounts domain routers — add one `include_router` per domain here.
- `api/v1/routers/r2.py` is the only infrastructure router (R2 uploads). Logic lives in `shared/storage/`.

### Domains Status

| Domain | Status | Notes |
|---|---|---|
| auth | Complete (old structure) | Google OAuth, JWT tokens, refresh/logout |
| users | Complete (old structure) | CRUD, role assignment, RBAC seeding. Roles: admin/participant/partner. No applicant role. |
| r2 | Complete (old structure) | Presigned upload/read URLs via Cloudflare R2 |
| participants | Not started | Profile, QR check-in, NFC token assignment |
| zones | Not started | Capacity, queue, status (red/amber/green) |
| points | Not started | Passport economy, earn/spend, leaderboard |
| schedule | Not started | Sessions, announcements, zone map data |
| incidents | Not started | Webhook ingestion from n8n/Google Forms |
| webhooks | Not started | n8n form payload ingestion |
| admin | Not started | Aggregated ops dashboard, overrides |

---

## What NOT to Do

- Do not leave the **Project State** section outdated after making changes. Update it before finishing any task.
- Do not add a flat `controllers/` file outside of a domain folder. Controllers belong inside `domains/<name>/controller.py`.
- Do not import raw `engine` or `Redis()` in service/business logic. Use `Depends()`.
- Do not put business logic in routers. Routers validate input and call services.
- Do not create models without adding their import to `app/models/__init__.py`.
- Do not modify `core/config.py`, `core/security.py`, or `main.py` without explicit review.
- Do not build incident tracking UI, network monitoring, chat/helpdesk, or registration flows. These are handled by external tools.
