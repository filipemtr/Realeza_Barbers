from datetime import timedelta
from pathlib import Path
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.audit import AuditRepository, CompositeAuditRepository, JsonlAuditRepository
from app.auth import SESSION_TTL, SessionRepository, UserRepository, create_auth_app
from app.bookings import AppointmentRepository, create_booking_router
from app.database import Database, SQLiteAppointmentRepository, SQLiteAuditRepository, SQLiteServiceRepository, SQLiteSessionRepository, SQLiteUserRepository
from app.resources import create_admin_router, create_service_router, create_availability_router


def create_app(
    *,
    user_repository: UserRepository | None = None,
    session_repository: SessionRepository | None = None,
    appointment_repository: AppointmentRepository | None = None,
    audit_repository: AuditRepository | None = None,
    service_repository=None,
    cookie_secure: bool | None = None,
    session_ttl: timedelta = SESSION_TTL,
    audit_log_path: Path = Path("logs/audit.jsonl"),
) -> FastAPI:
    """Monta a API; sem repositórios explícitos usa SQLite de produção local."""
    db = None
    if any(repo is None for repo in (user_repository, session_repository, appointment_repository, audit_repository, service_repository)):
        db = Database(os.getenv("REALEZA_DB_PATH", "data/realeza.db"))
        user_repository = user_repository or SQLiteUserRepository(db)
        session_repository = session_repository or SQLiteSessionRepository(db)
        appointment_repository = appointment_repository or SQLiteAppointmentRepository(db)
        service_repository = service_repository or SQLiteServiceRepository(db)
        audit_repository = audit_repository or SQLiteAuditRepository(db)

    assert user_repository is not None
    assert session_repository is not None
    assert appointment_repository is not None
    assert audit_repository is not None
    assert service_repository is not None

    if cookie_secure is None:
        secure_setting = os.getenv("REALEZA_COOKIE_SECURE")
        if secure_setting is not None:
            cookie_secure = secure_setting.strip().lower() in {"1", "true", "yes", "on"}
        else:
            configured_origins = (
                os.getenv("REALEZA_CORS_ORIGINS")
                or os.getenv("REALEZA_FRONTEND_URL")
                or "http://localhost:5173"
            )
            # HTTPS é o padrão quando a configuração indica uma origem de produção.
            cookie_secure = any(
                origin.strip().lower().startswith("https://")
                for origin in configured_origins.split(",")
            )

    configured_origins = os.getenv("REALEZA_CORS_ORIGINS")
    if configured_origins:
        allowed_origins = [origin.strip().rstrip("/") for origin in configured_origins.split(",") if origin.strip()]
    elif os.getenv("REALEZA_FRONTEND_URL"):
        allowed_origins = [os.environ["REALEZA_FRONTEND_URL"].strip().rstrip("/")]
    else:
        allowed_origins = ["http://localhost:5173"]

    combined_audit_repository = CompositeAuditRepository(
        JsonlAuditRepository(audit_log_path), audit_repository
    )
    app = create_auth_app(
        user_repository,
        session_repository,
        combined_audit_repository,
        cookie_secure=cookie_secure,
        session_ttl=session_ttl,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    app.include_router(
        create_booking_router(
            current_user_dependency=app.state.get_current_user,
            appointment_repository=appointment_repository,
            user_repository=user_repository,
            audit_repository=combined_audit_repository,
            service_repository=service_repository,
        )
    )
    app.include_router(
        create_service_router(
            service_repository=service_repository,
            current_user_dependency=app.state.get_current_user,
            audit_repository=combined_audit_repository,
        )
    )
    app.include_router(
        create_admin_router(
            user_repository=user_repository,
            current_user_dependency=app.state.get_current_user,
            audit_repository=combined_audit_repository,
            session_repository=session_repository,
        )
    )
    app.include_router(
        create_availability_router(
            service_repository=service_repository,
            user_repository=user_repository,
            appointment_repository=appointment_repository,
            current_user_dependency=app.state.get_current_user,
        )
    )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
