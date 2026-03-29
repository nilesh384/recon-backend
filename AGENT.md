# Backend Architecture & Best Practices

This guide serves as a central reference for the architectural decisions, design patterns, and tools utilized in this backend service. It is designed to get junior and senior engineers onboarded quickly by clarifying the separation of concerns.

## Tech Stack
- **Web Framework**: [FastAPI](https://fastapi.tiangolo.com/) - High performance API routing and validation.
- **ORM / Validation**: [SQLModel](https://sqlmodel.tiangolo.com/) - Combines SQLAlchemy and Pydantic. Classes function simultaneously as database schemas and data validators natively.
- **Database**: PostgreSQL (managed via SQLModel / `asyncpg` via NeonDB).
- **Caching / Messaging**: [Redis](https://redis.io/) (`redis.asyncio`).
- **Observability**: [Logfire](https://github.com/pydantic/logfire) - Automated full-stack telemetry and performance tracing.
- **Authentication**: Authlib (OAuth integrations) and Stateless JWTs with Stateful Refresh mechanisms.

---

## Directory Structure
The application employs a Model-Controller-Router pattern.

```text
backend/
├── main.py             # Entrypoint: Lifespan management, Logfire, Middlewares, App Mounts.
└── app/
    ├── api/            # API Route definitions and Dependency Injections.
    │   ├── v1/...      # Thin HTTP layer calling controllers.
    │   └── deps.py     # Central repository for `Depends()` (e.g. `get_db`, `get_redis`).
    ├── controllers/    # Pure business logic. NO HTTP context (No `Request`/`Response` objects natively).
    ├── core/           # Security, OAuth setup, and Pydantic Settings `config.py`.
    ├── db/             # Database async engine and connection definitions.
    ├── models/         # SQLModel database schemas (`table=True`).
    └── schemas/        # Pydantic validation models (e.g., `UserCreate`, `UserUpdate`).
```

---

## Core Practices

### 1. Lifespan Connection Management
Avoid global unmanaged connections. We use FastAPI's `@asynccontextmanager` in `main.py` explicitly for warming up infrastructure.
- **Redis**: The Redis connection pool is instantiated at startup and bound to the `FastAPI` instance state (`app.state.redis`). It is gracefully closed `aclose()` during server stop.
- **Postgres**: Similarly, the `engine` performs a `SELECT 1` warmup during startup and handles `dispose()` securely on shutdown.

### 2. Dependency Injection for Infrastructure
Never import a direct `Redis` or `Session` global client inside your inner business logic if possible.
Instead, your routers should pull connections via `Depends()` located in `api/deps.py`.
```python
# GOOD:
@router.get("/data")
async def get_data(redis: Redis = Depends(get_redis)):
    pass
```
*Why?* It allows for seamless mocking when unit testing router endpoints.

### 3. Separation of Concerns (Routers vs Controllers)
Routers (`app/api/routers/`) should be EXTREMELY thin. Their only job is parsing the HTTP `Request`, demanding dependencies (`Depends()`), and returning the API representation.
- Any heavy lifting, third-party API processing, or complex DB queries should be deferred to functions inside `app/controllers/`.
- **Reason**: You can execute controller logic in Celery Background Tasks or Python CLIs without needing to simulate a fake HTTP context.

### 4. Authentication Architecture
The backend uses a dual-token strategy secured natively through HTTP-only cookies in production:
1. **Access Tokens**: Short-lived (60 mins), cryptographically verified via Pydantic/FastAPI without needing a DB lookup (`stateless`).
2. **Refresh Tokens**: Long-lived (7 days), stored securely as hashes inside the database.
   - **Theft Detection Built-in**: If a user attempts to refresh with a token that is flagged as "revoked/already used", it signals token theft. The system immediately revokes **all** active tokens for that user to force a re-login.

### 5. Observability First
`Logfire` is wired into the foundation of the server (`main.py`).
Custom logic shouldn't need heavy manual `logging.info(...)` blocks unless describing a strict business state. `logfire.instrument_fastapi()` and `logfire.instrument_asyncpg()` will automatically trace request timings and raw database queries under the hood seamlessly.
To add context to operations quietly:
```python
import logfire
with logfire.span('calculating_heavy_metric'):
   do_metric_work()
```
