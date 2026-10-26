from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from typing import Callable, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field

from app.audit import AuditRepository, record_event
from app.auth import Role, User, UserRepository

CHANGE_CUTOFF = timedelta(hours=2)


@dataclass(frozen=True)
class Appointment:
    """Dados públicos de um agendamento."""

    id: str
    barber_id: str
    starts_at: datetime
    ends_at: datetime
    client_id: str | None = None
    service_id: str | None = None


class AppointmentConflictError(RuntimeError):
    """Indica conflito detectado atomically no repositório de persistência."""


class AppointmentRepository(Protocol):
    """Interface de persistência; não contém implementação de CRUD do banco."""

    # O adaptador SQLite implementa este contrato em app.database.
    # create/update usam transações para impedir conflitos simultâneos.
    async def list_for_barber(
        self, barber_id: str | None
    ) -> list[Appointment]: ...

    async def list_for_client(self, client_id: str) -> list[Appointment]: ...

    async def get_by_id(self, appointment_id: str) -> Appointment | None: ...

    async def has_conflict(
        self,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        excluding_id: str | None = None,
    ) -> bool: ...

    async def create(
        self,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        client_id: str | None = None,
        service_id: str | None = None,
    ) -> Appointment: ...

    async def update(
        self,
        appointment_id: str,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        service_id: str | None = None,
    ) -> Appointment | None: ...

    async def delete(self, appointment_id: str) -> bool: ...


class AppointmentInput(BaseModel):
    """Entrada para criar ou alterar um agendamento."""

    barber_id: str | None = Field(default=None, min_length=1, max_length=128)
    client_id: str | None = Field(default=None, min_length=1, max_length=128)
    service_id: str | None = Field(default=None, min_length=1, max_length=128)
    starts_at: datetime
    ends_at: datetime
    confirmed: Literal[True]


class AppointmentConfirmation(BaseModel):
    """Confirma explicitamente o cancelamento de um agendamento."""

    confirmed: Literal[True]


async def _reject_booking_input(
    audit_repository: AuditRepository,
    user: User,
    *,
    operation: str,
    reason: str,
    detail: str,
    starts_at: datetime | None = None,
    ends_at: datetime | None = None,
    target_id: str | None = None,
) -> None:
    await record_event(
        audit_repository,
        actor_user_id=user.id,
        action="appointment.request.rejected",
        details={
            "actor_role": user.role.value,
            "operation": operation,
            "reason": reason,
            "starts_at": starts_at.isoformat() if starts_at is not None else None,
            "ends_at": ends_at.isoformat() if ends_at is not None else None,
            "target_id": target_id,
        },
    )
    raise HTTPException(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        detail=detail,
    )


async def _check_interval(
    starts_at: datetime,
    ends_at: datetime,
    audit_repository: AuditRepository,
    user: User,
    *,
    operation: str,
) -> None:
    """Exige instantes com fuso horário, início futuro e término posterior."""
    for value in (starts_at, ends_at):
        if value.tzinfo is None or value.utcoffset() is None:
            await _reject_booking_input(
                audit_repository,
                user,
                operation=operation,
                reason="timezone_missing",
                detail="Data e hora devem incluir fuso horário",
                starts_at=starts_at,
                ends_at=ends_at,
            )
    if ends_at <= starts_at:
        await _reject_booking_input(
            audit_repository,
            user,
            operation=operation,
            reason="invalid_interval",
            detail="O término deve ser posterior ao início",
            starts_at=starts_at,
            ends_at=ends_at,
        )
    if starts_at <= datetime.now(timezone.utc):
        await _reject_booking_input(
            audit_repository,
            user,
            operation=operation,
            reason="appointment_in_past",
            detail="Não é permitido agendar no passado",
            starts_at=starts_at,
            ends_at=ends_at,
        )


async def _deny_action(
    audit_repository: AuditRepository,
    user: User,
    *,
    operation: str,
    reason: str,
    detail: str,
    appointment_id: str | None = None,
) -> None:
    details: dict[str, str | None] = {
        "actor_role": user.role.value if isinstance(user.role, Role) else str(user.role),
        "operation": operation,
        "reason": reason,
        "appointment_id": appointment_id,
    }
    await record_event(
        audit_repository,
        actor_user_id=user.id,
        action="authorization.denied",
        details=details,
    )
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


async def _ensure_before_cutoff(
    starts_at: datetime,
    audit_repository: AuditRepository,
    user: User,
    *,
    operation: str,
    appointment_id: str,
) -> None:
    if starts_at.tzinfo is None or starts_at.utcoffset() is None:
        raise ValueError("starts_at do agendamento deve incluir fuso horário")
    cutoff = starts_at.astimezone(timezone.utc) - CHANGE_CUTOFF
    if datetime.now(timezone.utc) > cutoff:
        await _deny_action(
            audit_repository,
            user,
            operation=operation,
            reason="two_hour_cutoff_exceeded",
            detail="Esta operação só é permitida até 2 horas antes do agendamento",
            appointment_id=appointment_id,
        )


async def _validate_barber(
    users: UserRepository,
    barber_id: str,
    audit_repository: AuditRepository,
    user: User,
    *,
    operation: str,
) -> None:
    barber = await users.find_by_id(barber_id)
    if barber is None or not barber.is_active or barber.role is not Role.BARBER:
        await _reject_booking_input(
            audit_repository,
            user,
            operation=operation,
            reason="barber_missing_inactive_or_wrong_role",
            detail="O barbeiro informado não existe ou não está ativo",
            target_id=barber_id,
        )


async def _validate_client(
    users: UserRepository,
    client_id: str,
    audit_repository: AuditRepository,
    user: User,
    *,
    operation: str,
) -> None:
    client = await users.find_by_id(client_id)
    if client is None or not client.is_active or client.role is not Role.USER:
        await _reject_booking_input(
            audit_repository,
            user,
            operation=operation,
            reason="client_missing_inactive_or_wrong_role",
            detail="O cliente informado não existe ou não está ativo",
            target_id=client_id,
        )


async def _ensure_known_role(
    user: User,
    audit_repository: AuditRepository,
    *,
    operation: str,
) -> None:
    if not isinstance(user.role, Role):
        await _deny_action(
            audit_repository,
            user,
            operation=operation,
            reason="invalid_role",
            detail="Perfil de usuário inválido",
        )


async def _validate_service(service_repository, service_id: str, audit_repository: AuditRepository, user: User, *, operation: str):
    if service_repository is None:
        return
    service = await service_repository.get(service_id)
    if service is None or not service.is_active:
        await _reject_booking_input(
            audit_repository, user, operation=operation,
            reason="service_missing_or_inactive",
            detail="O serviço informado não existe ou está inativo",
            target_id=service_id,
        )
    return service


async def _validate_business_slot(
    starts_at: datetime,
    ends_at: datetime,
    audit_repository: AuditRepository,
    user: User,
    *,
    operation: str,
) -> None:
    """Impede chamadas diretas à API de contornar os horários mostrados na agenda."""
    from zoneinfo import ZoneInfo

    business_tz = ZoneInfo("America/Sao_Paulo")
    local_start = starts_at.astimezone(business_tz)
    local_end = ends_at.astimezone(business_tz)
    valid_start = (
        local_start.hour >= 8
        and local_start.hour < 18
        and local_start.minute in (0, 30)
        and local_start.second == 0
        and local_start.microsecond == 0
    )
    valid_end = (local_end.hour < 18) or (
        local_end.hour == 18 and local_end.minute == 0 and local_end.second == 0 and local_end.microsecond == 0
    )
    if (
        not valid_start
        or not valid_end
        or local_start.date() != local_end.date()
    ):
        await _reject_booking_input(
            audit_repository,
            user,
            operation=operation,
            reason="outside_business_hours_or_invalid_slot",
            detail="Escolha um horário disponível entre 08:00 e 18:00, em intervalos de 30 minutos",
            starts_at=starts_at,
            ends_at=ends_at,
        )


def create_booking_router(
    *,
    current_user_dependency: Callable[..., User],
    appointment_repository: AppointmentRepository,
    user_repository: UserRepository,
    audit_repository: AuditRepository,
    service_repository=None,
) -> APIRouter:
    """Cria rotas de agendamento que aplicam autorização e regras antes do CRUD."""
    router = APIRouter(prefix="/appointments", tags=["appointments"])

    @router.get("")
    async def list_appointments(
        user: User = Depends(current_user_dependency),
    ) -> list[Appointment]:
        await _ensure_known_role(
            user, audit_repository, operation="appointments.list"
        )
        if user.role is Role.USER:
            appointments = await appointment_repository.list_for_client(user.id)
            scope = "client"
        else:
            # Admin consulta todos; barbeiro recebe apenas os próprios registros.
            barber_id = None if user.role is Role.ADMIN else user.id
            appointments = await appointment_repository.list_for_barber(barber_id)
            scope = "all" if user.role is Role.ADMIN else "barber"
        await record_event(
            audit_repository,
            actor_user_id=user.id,
            action="appointments.listed",
            details={
                "actor_role": user.role.value,
                "scope": scope,
                "result_count": str(len(appointments)),
            },
        )
        return appointments

    @router.post("", status_code=status.HTTP_201_CREATED)
    async def create_appointment(
        payload: AppointmentInput,
        user: User = Depends(current_user_dependency),
    ) -> Appointment:
        await _ensure_known_role(
            user, audit_repository, operation="appointment.create"
        )
        await _check_interval(
            payload.starts_at,
            payload.ends_at,
            audit_repository,
            user,
            operation="appointment.create",
        )
        if payload.service_id is not None:
            service = await _validate_service(service_repository, payload.service_id, audit_repository, user, operation="appointment.create")
            if service is not None:
                expected_end = payload.starts_at + timedelta(minutes=service.duration_minutes)
                if expected_end != payload.ends_at:
                    await _reject_booking_input(
                        audit_repository, user, operation="appointment.create",
                        reason="service_duration_mismatch",
                        detail="O horário final não corresponde à duração do serviço",
                        starts_at=payload.starts_at, ends_at=payload.ends_at,
                    )
                await _validate_business_slot(
                    payload.starts_at, payload.ends_at, audit_repository, user,
                    operation="appointment.create",
                )

        if user.role is Role.BARBER:
            if payload.barber_id is not None and payload.barber_id != user.id:
                await _deny_action(
                    audit_repository,
                    user,
                    operation="appointment.create",
                    reason="barber_targeted_another_barber",
                    detail="Barbeiros só podem criar os próprios agendamentos",
                )
            barber_id = user.id
            client_id = payload.client_id
            if client_id is not None:
                await _validate_client(
                    user_repository,
                    client_id,
                    audit_repository,
                    user,
                    operation="appointment.create",
                )
        elif user.role in (Role.USER, Role.ADMIN):
            if payload.barber_id is None:
                await _reject_booking_input(
                    audit_repository,
                    user,
                    operation="appointment.create",
                    reason="barber_not_selected",
                    detail="Informe o barbeiro responsável pelo agendamento",
                )
            barber_id = payload.barber_id
            await _validate_barber(
                user_repository,
                barber_id,
                audit_repository,
                user,
                operation="appointment.create",
            )
            if user.role is Role.USER:
                client_id = user.id
            else:
                client_id = payload.client_id
                if client_id is not None:
                    await _validate_client(
                        user_repository,
                        client_id,
                        audit_repository,
                        user,
                        operation="appointment.create",
                    )
        else:
            await _deny_action(
                audit_repository,
                user,
                operation="appointment.create",
                reason="role_not_allowed",
                detail="Perfil sem permissão para criar agendamentos",
            )

        if await appointment_repository.has_conflict(
            barber_id, payload.starts_at, payload.ends_at
        ):
            await record_event(
                audit_repository,
                actor_user_id=user.id,
                action="appointment.create.rejected",
                details={
                    "actor_role": user.role.value,
                    "reason": "schedule_conflict",
                    "barber_id": barber_id,
                    "client_id": client_id,
                    "starts_at": payload.starts_at.isoformat(),
                    "ends_at": payload.ends_at.isoformat(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O barbeiro já possui um agendamento nesse horário",
            )

        try:
            appointment = await appointment_repository.create(
                barber_id,
                payload.starts_at,
                payload.ends_at,
                client_id=client_id,
                service_id=payload.service_id,
            )
        except TypeError:
            # Repositórios legados usados nos testes podem não conhecer service_id.
            appointment = await appointment_repository.create(
                barber_id, payload.starts_at, payload.ends_at, client_id=client_id
            )
        except AppointmentConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O barbeiro já possui um agendamento nesse horário",
            )
        await record_event(
            audit_repository,
            actor_user_id=user.id,
            action="appointment.created",
            details={
                "appointment_id": appointment.id,
                "actor_role": user.role.value,
                "barber_id": barber_id,
                "client_id": client_id,
                "starts_at": appointment.starts_at.isoformat(),
                "ends_at": appointment.ends_at.isoformat(),
            },
        )
        return appointment

    @router.put("/{appointment_id}")
    async def update_appointment(
        appointment_id: str,
        payload: AppointmentInput,
        user: User = Depends(current_user_dependency),
    ) -> Appointment:
        await _ensure_known_role(
            user, audit_repository, operation="appointment.update"
        )
        existing = await appointment_repository.get_by_id(appointment_id)
        if existing is None:
            await record_event(
                audit_repository,
                actor_user_id=user.id,
                action="appointment.update.rejected",
                details={
                    "actor_role": user.role.value,
                    "reason": "appointment_not_found",
                    "appointment_id": appointment_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agendamento não encontrado",
            )
        if user.role is Role.USER and existing.client_id != user.id:
            await _deny_action(
                audit_repository,
                user,
                operation="appointment.update",
                reason="not_appointment_client",
                detail="Clientes só podem alterar os próprios agendamentos",
                appointment_id=appointment_id,
            )
        if user.role is Role.USER:
            await _ensure_before_cutoff(
                existing.starts_at,
                audit_repository,
                user,
                operation="appointment.update",
                appointment_id=appointment_id,
            )
        if user.role is Role.BARBER and existing.barber_id != user.id:
            await _deny_action(
                audit_repository,
                user,
                operation="appointment.update",
                reason="not_assigned_barber",
                detail="Barbeiros só podem alterar os próprios agendamentos",
                appointment_id=appointment_id,
            )

        await _check_interval(
            payload.starts_at,
            payload.ends_at,
            audit_repository,
            user,
            operation="appointment.update",
        )
        effective_service_id = payload.service_id or existing.service_id
        if effective_service_id is not None:
            service = await _validate_service(service_repository, effective_service_id, audit_repository, user, operation="appointment.update")
            if service is not None:
                expected_end = payload.starts_at + timedelta(minutes=service.duration_minutes)
                if expected_end != payload.ends_at:
                    await _reject_booking_input(
                        audit_repository, user, operation="appointment.update",
                        reason="service_duration_mismatch",
                        detail="O horário final não corresponde à duração do serviço",
                        starts_at=payload.starts_at, ends_at=payload.ends_at,
                    )
                await _validate_business_slot(
                    payload.starts_at, payload.ends_at, audit_repository, user,
                    operation="appointment.update",
                )
        barber_id = payload.barber_id or existing.barber_id
        if user.role is Role.BARBER and barber_id != user.id:
            await _deny_action(
                audit_repository,
                user,
                operation="appointment.update",
                reason="barber_transfer_attempt",
                detail="Barbeiros não podem transferir agendamentos",
                appointment_id=appointment_id,
            )
        if user.role is Role.USER:
            await _validate_barber(
                user_repository,
                barber_id,
                audit_repository,
                user,
                operation="appointment.update",
            )
        elif user.role is Role.ADMIN:
            await _validate_barber(
                user_repository,
                barber_id,
                audit_repository,
                user,
                operation="appointment.update",
            )

        if await appointment_repository.has_conflict(
            barber_id,
            payload.starts_at,
            payload.ends_at,
            excluding_id=appointment_id,
        ):
            await record_event(
                audit_repository,
                actor_user_id=user.id,
                action="appointment.update.rejected",
                details={
                    "actor_role": user.role.value,
                    "reason": "schedule_conflict",
                    "appointment_id": appointment_id,
                    "barber_id": barber_id,
                    "starts_at": payload.starts_at.isoformat(),
                    "ends_at": payload.ends_at.isoformat(),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O barbeiro já possui um agendamento nesse horário",
            )

        try:
            appointment = await appointment_repository.update(
                appointment_id, barber_id, payload.starts_at, payload.ends_at, service_id=payload.service_id
            )
        except TypeError:
            appointment = await appointment_repository.update(
                appointment_id, barber_id, payload.starts_at, payload.ends_at
            )
        except AppointmentConflictError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="O barbeiro já possui um agendamento nesse horário",
            )
        if appointment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agendamento não encontrado",
            )
        await record_event(
            audit_repository,
            actor_user_id=user.id,
            action="appointment.updated",
            details={
                "appointment_id": appointment.id,
                "actor_role": user.role.value,
                "barber_id": barber_id,
                "client_id": appointment.client_id,
                "previous_starts_at": existing.starts_at.isoformat(),
                "previous_ends_at": existing.ends_at.isoformat(),
                "starts_at": appointment.starts_at.isoformat(),
                "ends_at": appointment.ends_at.isoformat(),
            },
        )
        return appointment

    @router.delete(
        "/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT
    )
    async def delete_appointment(
        appointment_id: str,
        payload: AppointmentConfirmation,
        response: Response,
        user: User = Depends(current_user_dependency),
    ) -> Response:
        await _ensure_known_role(
            user, audit_repository, operation="appointment.cancel"
        )
        existing = await appointment_repository.get_by_id(appointment_id)
        if existing is None:
            await record_event(
                audit_repository,
                actor_user_id=user.id,
                action="appointment.cancel.rejected",
                details={
                    "actor_role": user.role.value,
                    "reason": "appointment_not_found",
                    "appointment_id": appointment_id,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agendamento não encontrado",
            )
        if user.role is Role.USER and existing.client_id != user.id:
            await _deny_action(
                audit_repository,
                user,
                operation="appointment.cancel",
                reason="not_appointment_client",
                detail="Clientes só podem cancelar os próprios agendamentos",
                appointment_id=appointment_id,
            )
        if user.role is Role.BARBER and existing.barber_id != user.id:
            await _deny_action(
                audit_repository,
                user,
                operation="appointment.cancel",
                reason="not_assigned_barber",
                detail="Barbeiros só podem excluir os próprios agendamentos",
                appointment_id=appointment_id,
            )
        if user.role in (Role.USER, Role.BARBER):
            await _ensure_before_cutoff(
                existing.starts_at,
                audit_repository,
                user,
                operation="appointment.cancel",
                appointment_id=appointment_id,
            )

        if not await appointment_repository.delete(appointment_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Agendamento não encontrado",
            )
        await record_event(
            audit_repository,
            actor_user_id=user.id,
            action="appointment.deleted",
            details={
                "appointment_id": appointment_id,
                "actor_role": user.role.value,
                "barber_id": existing.barber_id,
                "client_id": existing.client_id,
                "starts_at": existing.starts_at.isoformat(),
                "ends_at": existing.ends_at.isoformat(),
            },
        )
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    return router
