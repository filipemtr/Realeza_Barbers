from __future__ import annotations

from typing import Callable
import asyncio
import re
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.audit import AuditRepository, record_event
from app.auth import Role, User
from app.authorization import require_admin


class ServiceInput(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=500)
    price_cents: int = Field(ge=0, le=10_000_000)
    duration_minutes: int = Field(gt=0, le=480)
    is_active: bool = True


def _normalize_and_validate_email(value: str) -> str:
    email = value.strip().lower()
    # Validação básica de formato sem adicionar dependência extra ao projeto.
    if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise ValueError("Informe um e-mail válido")
    return email


def _validate_password_bytes(value: str | None) -> str | None:
    if value is not None and len(value.encode("utf-8")) > 72:
        raise ValueError("A senha não pode exceder 72 bytes em UTF-8")
    return value


class UserInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.USER
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return _normalize_and_validate_email(value)

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str) -> str:
        return _validate_password_bytes(value) or value


class UserUpdateInput(BaseModel):
    email: str | None = Field(default=None, min_length=3, max_length=254)
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: Role | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        return _normalize_and_validate_email(value) if value is not None else None

    @field_validator("password")
    @classmethod
    def password_byte_limit(cls, value: str | None) -> str | None:
        return _validate_password_bytes(value)


def create_service_router(*, service_repository, current_user_dependency: Callable[..., User], audit_repository: AuditRepository) -> APIRouter:
    router = APIRouter(prefix="/services", tags=["services"])

    @router.get("")
    async def list_services():
        services = await service_repository.list()
        return services

    @router.get("/{service_id}")
    async def get_service(service_id: str):
        service = await service_repository.get(service_id)
        if service is None or not service.is_active:
            raise HTTPException(status_code=404, detail="Serviço não encontrado")
        return service

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_service(payload: ServiceInput, user: User = Depends(current_user_dependency)):
        require_admin(user)
        try:
            service = await service_repository.create(payload.name, payload.description, payload.price_cents, payload.duration_minutes)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Já existe um serviço com esse nome") from exc
        await record_event(audit_repository, actor_user_id=user.id, action="service.created", details={"service_id": service.id, "name": service.name})
        return service

    @router.put("/{service_id}")
    async def update_service(service_id: str, payload: ServiceInput, user: User = Depends(current_user_dependency)):
        require_admin(user)
        try:
            service = await service_repository.update(service_id, name=payload.name, description=payload.description, price_cents=payload.price_cents, duration_minutes=payload.duration_minutes, is_active=payload.is_active)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Já existe um serviço com esse nome") from exc
        if service is None:
            raise HTTPException(status_code=404, detail="Serviço não encontrado")
        await record_event(audit_repository, actor_user_id=user.id, action="service.updated", details={"service_id": service.id})
        return service

    @router.delete("/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_service(service_id: str, user: User = Depends(current_user_dependency)):
        require_admin(user)
        if not await service_repository.delete(service_id):
            raise HTTPException(status_code=404, detail="Serviço não encontrado")
        await record_event(audit_repository, actor_user_id=user.id, action="service.deactivated", details={"service_id": service_id})
        return None

    return router


def create_admin_router(*, user_repository, current_user_dependency: Callable[..., User], audit_repository: AuditRepository, session_repository=None) -> APIRouter:
    router = APIRouter(prefix="/admin", tags=["admin"])

    @router.get("/users")
    async def list_users(user: User = Depends(current_user_dependency)):
        require_admin(user)
        users = await user_repository.list()
        return [
            {"id": item.id, "email": item.email, "role": item.role.value, "is_active": item.is_active}
            for item in users
        ]

    @router.post("/users", status_code=status.HTTP_201_CREATED)
    async def create_user(payload: UserInput, user: User = Depends(current_user_dependency)):
        require_admin(user)
        from app.auth import hash_password
        if await user_repository.find_by_email(payload.email):
            raise HTTPException(status_code=409, detail="E-mail já cadastrado")
        try:
            password_hash = await asyncio.to_thread(hash_password, payload.password)
            created = await user_repository.create(payload.email, password_hash, payload.role, is_active=payload.is_active)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="E-mail já cadastrado") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await record_event(audit_repository, actor_user_id=user.id, action="user.created", details={"target_user_id": created.id, "role": created.role.value})
        return {"id": created.id, "email": created.email, "role": created.role.value, "is_active": created.is_active}

    @router.put("/users/{user_id}")
    async def update_user(user_id: str, payload: UserUpdateInput, user: User = Depends(current_user_dependency)):
        require_admin(user)
        from app.auth import hash_password
        if user_id == user.id and (
            payload.is_active is False
            or (payload.role is not None and payload.role is not Role.ADMIN)
        ):
            raise HTTPException(status_code=400, detail="Não é permitido desativar ou rebaixar a própria conta administradora")
        try:
            password_hash = await asyncio.to_thread(hash_password, payload.password) if payload.password is not None else None
            updated = await user_repository.update(user_id, email=payload.email, role=payload.role, is_active=payload.is_active, password_hash=password_hash)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="E-mail já cadastrado") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        # Alterações sensíveis invalidam sessões existentes; a verificação mantém
        # compatibilidade com repositórios fake usados em testes/injeção.
        if session_repository is not None and (
            payload.password is not None or payload.is_active is not None or payload.role is not None
        ):
            revoke_sessions = getattr(session_repository, "delete_for_user", None)
            if revoke_sessions is not None:
                await revoke_sessions(user_id)
        await record_event(audit_repository, actor_user_id=user.id, action="user.updated", details={"target_user_id": user_id})
        return {"id": updated.id, "email": updated.email, "role": updated.role.value, "is_active": updated.is_active}

    @router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_user(user_id: str, user: User = Depends(current_user_dependency)):
        require_admin(user)
        if user_id == user.id:
            raise HTTPException(status_code=400, detail="Não é permitido excluir o próprio usuário administrador")
        try:
            deleted = await user_repository.delete(user_id)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Não é possível excluir um barbeiro com agendamentos vinculados; desative o usuário em vez disso") from exc
        if not deleted:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")
        await record_event(audit_repository, actor_user_id=user.id, action="user.deleted", details={"target_user_id": user_id})
        return None

    @router.get("/barbers")
    async def list_barbers(user: User = Depends(current_user_dependency)):
        require_admin(user)
        users = await user_repository.list(Role.BARBER)
        return [{"id": item.id, "email": item.email, "is_active": item.is_active} for item in users]

    @router.get("/clients")
    async def list_clients(user: User = Depends(current_user_dependency)):
        require_admin(user)
        users = await user_repository.list(Role.USER)
        return [{"id": item.id, "email": item.email, "is_active": item.is_active} for item in users]

    return router


def create_availability_router(*, service_repository, user_repository, appointment_repository, current_user_dependency: Callable[..., User]) -> APIRouter:
    from datetime import date, datetime, time, timedelta, timezone
    from zoneinfo import ZoneInfo

    router = APIRouter(prefix="/availability", tags=["availability"])

    @router.get("")
    async def availability(service_id: str, date_value: str, user: User = Depends(current_user_dependency)):
        try:
            selected_date = date.fromisoformat(date_value)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="date_value deve estar no formato YYYY-MM-DD") from exc
        service = await service_repository.get(service_id)
        if service is None or not service.is_active:
            raise HTTPException(status_code=404, detail="Serviço não encontrado")
        barbers = await user_repository.list(Role.BARBER)
        result = []
        for barber in barbers:
            if not barber.is_active:
                continue
            slots = []
            business_tz = ZoneInfo("America/Sao_Paulo")
            cursor = datetime.combine(selected_date, time(8, 0), tzinfo=business_tz).astimezone(timezone.utc)
            closing = datetime.combine(selected_date, time(18, 0), tzinfo=business_tz).astimezone(timezone.utc)
            while cursor + timedelta(minutes=service.duration_minutes) <= closing:
                end = cursor + timedelta(minutes=service.duration_minutes)
                if cursor > datetime.now(timezone.utc) and not await appointment_repository.has_conflict(barber.id, cursor, end):
                    slots.append({"starts_at": cursor.isoformat(), "ends_at": end.isoformat()})
                cursor += timedelta(minutes=30)
            result.append({"barber_id": barber.id, "email": barber.email, "slots": slots})
        return {"date": selected_date.isoformat(), "service_id": service_id, "service_duration_minutes": service.duration_minutes, "barbers": result}

    return router
