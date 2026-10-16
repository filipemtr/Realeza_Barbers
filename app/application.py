from datetime import timedelta
from pathlib import Path

from fastapi import FastAPI

from app.audit import (
    AuditRepository,
    CompositeAuditRepository,
    JsonlAuditRepository,
)
from app.auth import (
    SESSION_TTL,
    SessionRepository,
    UserRepository,
    create_auth_app,
)
from app.bookings import AppointmentRepository, create_booking_router


def create_app(
    *,
    user_repository: UserRepository,
    session_repository: SessionRepository,
    appointment_repository: AppointmentRepository,
    audit_repository: AuditRepository,
    cookie_secure: bool = True,
    session_ttl: timedelta = SESSION_TTL,
    audit_log_path: Path = Path("logs/audit.jsonl"),
) -> FastAPI:
    """Liga autenticação, autorização, agendamentos e auditoria em uma API."""
    combined_audit_repository = CompositeAuditRepository(
        JsonlAuditRepository(audit_log_path),
        audit_repository,
    )
    app = create_auth_app(
        user_repository,
        session_repository,
        combined_audit_repository,
        cookie_secure=cookie_secure,
        session_ttl=session_ttl,
    )
    app.include_router(
        create_booking_router(
            current_user_dependency=app.state.get_current_user,
            appointment_repository=appointment_repository,
            user_repository=user_repository,
            audit_repository=combined_audit_repository,
        )
    )
    return app
