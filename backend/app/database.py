from __future__ import annotations

import asyncio
import json
import sqlite3
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import aiosqlite

from app.audit import AuditEvent, AuditRepository
from app.auth import Role, StoredSession, User, UserRepository, SessionRepository
from app.bookings import Appointment, AppointmentRepository, AppointmentConflictError


SCHEMA_PATH = Path(__file__).with_name("schema.sql")


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    description: str
    price_cents: int
    duration_minutes: int
    is_active: bool = True


class Database:
    def __init__(self, path: str | Path = "data/realeza.db") -> None:
        self.path = Path(path)
        self._write_lock = asyncio.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.path) as db:
            db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys = ON")
            await db.execute("PRAGMA busy_timeout = 5000")
            yield db

    async def initialize(self) -> None:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")

        async with self.connect() as db:
            await db.executescript(schema)
            await db.commit()

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        async with self.connect() as db:
            await db.execute(sql, params)
            await db.commit()


class SQLiteUserRepository(UserRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def find_by_email(self, email: str) -> User | None:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "SELECT id, email, password_hash, is_active, role "
                "FROM users WHERE lower(email)=lower(?)",
                (email,),
            )
            row = await cursor.fetchone()
            return _user_from_row(row) if row else None

    async def find_by_id(self, user_id: str) -> User | None:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "SELECT id, email, password_hash, is_active, role "
                "FROM users WHERE id=?",
                (user_id,),
            )
            row = await cursor.fetchone()
            return _user_from_row(row) if row else None

    async def list(self, role: Role | None = None) -> list[User]:
        query = "SELECT id, email, password_hash, is_active, role FROM users"
        params: tuple[Any, ...] = ()

        if role is not None:
            query += " WHERE role=?"
            params = (role.value,)

        query += " ORDER BY email"

        async with self._db.connect() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [_user_from_row(row) for row in rows]

    async def create(
        self,
        email: str,
        password_hash: str,
        role: Role = Role.USER,
        *,
        is_active: bool = True,
    ) -> User:
        user_id = str(uuid4())

        await self._db.execute(
            "INSERT INTO users(id,email,password_hash,is_active,role) "
            "VALUES(?,?,?,?,?)",
            (user_id, email, password_hash, int(is_active), role.value),
        )

        return User(user_id, email, password_hash, is_active, role)

    async def update(
        self,
        user_id: str,
        *,
        email: str | None = None,
        role: Role | None = None,
        is_active: bool | None = None,
        password_hash: str | None = None,
    ) -> User | None:
        current = await self.find_by_id(user_id)

        if current is None:
            return None

        new_email = email if email is not None else current.email
        new_role = role if role is not None else current.role
        new_active = is_active if is_active is not None else current.is_active
        new_hash = password_hash if password_hash is not None else current.password_hash

        await self._db.execute(
            "UPDATE users SET email=?, password_hash=?, is_active=?, role=? "
            "WHERE id=?",
            (new_email, new_hash, int(new_active), new_role.value, user_id),
        )

        return User(user_id, new_email, new_hash, new_active, new_role)

    async def delete(self, user_id: str) -> bool:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "DELETE FROM users WHERE id=?",
                (user_id,),
            )
            await db.commit()
            return cursor.rowcount > 0


class SQLiteSessionRepository(SessionRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self,
        token_hash: str,
        user_id: str,
        expires_at: datetime,
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO sessions(token_hash,user_id,expires_at) "
            "VALUES(?,?,?)",
            (token_hash, user_id, _dt(expires_at)),
        )

    async def find_by_token_hash(
        self,
        token_hash: str,
    ) -> StoredSession | None:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "SELECT user_id, expires_at FROM sessions WHERE token_hash=?",
                (token_hash,),
            )
            row = await cursor.fetchone()

            if not row:
                return None

            return StoredSession(
                row["user_id"],
                _parse_dt(row["expires_at"]),
            )

    async def delete_by_token_hash(self, token_hash: str) -> None:
        await self._db.execute(
            "DELETE FROM sessions WHERE token_hash=?",
            (token_hash,),
        )

    async def delete_for_user(self, user_id: str) -> None:
        """Revoga todas as sessões do usuário após alterações sensíveis."""
        await self._db.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))


class SQLiteAuditRepository(AuditRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(self, event: AuditEvent) -> None:
        await self._db.execute(
            "INSERT INTO audit_logs(actor_user_id,action,occurred_at,details_json) "
            "VALUES(?,?,?,?)",
            (
                event.actor_user_id,
                event.action,
                _dt(event.occurred_at),
                json.dumps(event.details, ensure_ascii=False),
            ),
        )


class SQLiteAppointmentRepository(AppointmentRepository):
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list_for_barber(
        self,
        barber_id: str | None,
    ) -> list[Appointment]:
        query = (
            "SELECT id, barber_id, client_id, service_id, starts_at, ends_at "
            "FROM appointments"
        )
        params: tuple[Any, ...] = ()

        if barber_id is not None:
            query += " WHERE barber_id=?"
            params = (barber_id,)

        query += " ORDER BY starts_at"

        async with self._db.connect() as db:
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [_appointment_from_row(row) for row in rows]

    async def list_for_client(
        self,
        client_id: str,
    ) -> list[Appointment]:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "SELECT id, barber_id, client_id, service_id, starts_at, ends_at "
                "FROM appointments WHERE client_id=? ORDER BY starts_at",
                (client_id,),
            )
            rows = await cursor.fetchall()
            return [_appointment_from_row(row) for row in rows]

    async def get_by_id(
        self,
        appointment_id: str,
    ) -> Appointment | None:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "SELECT id, barber_id, client_id, service_id, starts_at, ends_at "
                "FROM appointments WHERE id=?",
                (appointment_id,),
            )
            row = await cursor.fetchone()
            return _appointment_from_row(row) if row else None

    async def has_conflict(
        self,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        excluding_id: str | None = None,
    ) -> bool:
        async with self._db.connect() as db:
            query = (
                "SELECT 1 FROM appointments "
                "WHERE barber_id=? AND starts_at < ? AND ends_at > ?"
            )
            params: list[Any] = [
                barber_id,
                _dt(ends_at),
                _dt(starts_at),
            ]

            if excluding_id is not None:
                query += " AND id <> ?"
                params.append(excluding_id)

            cursor = await db.execute(
                query + " LIMIT 1",
                tuple(params),
            )
            return await cursor.fetchone() is not None

    async def create(
        self,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        client_id: str | None = None,
        service_id: str | None = None,
    ) -> Appointment:
        appointment_id = str(uuid4())

        async with self._db._write_lock:
            async with self._db.connect() as db:
                await db.execute("BEGIN IMMEDIATE")

                try:
                    conflict = await self._has_conflict_conn(
                        db,
                        barber_id,
                        starts_at,
                        ends_at,
                    )

                    if conflict:
                        raise AppointmentConflictError

                    await db.execute(
                        "INSERT INTO appointments("
                        "id,barber_id,client_id,service_id,starts_at,ends_at,status"
                        ") VALUES(?,?,?,?,?,?,?)",
                        (
                            appointment_id,
                            barber_id,
                            client_id,
                            service_id,
                            _dt(starts_at),
                            _dt(ends_at),
                            "scheduled",
                        ),
                    )

                    await db.commit()

                except Exception:
                    await db.rollback()
                    raise

        return Appointment(
            appointment_id,
            barber_id,
            starts_at,
            ends_at,
            client_id,
            service_id,
        )

    async def update(
        self,
        appointment_id: str,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        service_id: str | None = None,
    ) -> Appointment | None:
        async with self._db._write_lock:
            async with self._db.connect() as db:
                await db.execute("BEGIN IMMEDIATE")

                try:
                    cursor = await db.execute(
                        "SELECT id, client_id, service_id "
                        "FROM appointments WHERE id=?",
                        (appointment_id,),
                    )
                    row = await cursor.fetchone()

                    if row is None:
                        await db.rollback()
                        return None

                    conflict = await self._has_conflict_conn(
                        db,
                        barber_id,
                        starts_at,
                        ends_at,
                        excluding_id=appointment_id,
                    )

                    if conflict:
                        raise AppointmentConflictError

                    await db.execute(
                        "UPDATE appointments SET barber_id=?, starts_at=?, "
                        "ends_at=?, service_id=COALESCE(?,service_id) WHERE id=?",
                        (
                            barber_id,
                            _dt(starts_at),
                            _dt(ends_at),
                            service_id,
                            appointment_id,
                        ),
                    )

                    await db.commit()

                    actual_service_id = (
                        service_id
                        if service_id is not None
                        else row["service_id"]
                        if "service_id" in row.keys()
                        else None
                    )

                    return Appointment(
                        appointment_id,
                        barber_id,
                        starts_at,
                        ends_at,
                        row["client_id"],
                        actual_service_id,
                    )

                except Exception:
                    await db.rollback()
                    raise

    async def delete(self, appointment_id: str) -> bool:
        async with self._db._write_lock:
            async with self._db.connect() as db:
                cursor = await db.execute(
                    "DELETE FROM appointments WHERE id=?",
                    (appointment_id,),
                )
                await db.commit()
                return cursor.rowcount > 0

    async def _has_conflict_conn(
        self,
        db: aiosqlite.Connection,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        excluding_id: str | None = None,
    ) -> bool:
        query = (
            "SELECT 1 FROM appointments "
            "WHERE barber_id=? AND starts_at < ? AND ends_at > ?"
        )
        params: list[Any] = [
            barber_id,
            _dt(ends_at),
            _dt(starts_at),
        ]

        if excluding_id is not None:
            query += " AND id <> ?"
            params.append(excluding_id)

        cursor = await db.execute(
            query + " LIMIT 1",
            tuple(params),
        )
        return await cursor.fetchone() is not None


class SQLiteServiceRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def list(
        self,
        *,
        include_inactive: bool = False,
    ) -> list[Service]:
        query = (
            "SELECT id,name,description,price_cents,duration_minutes,is_active "
            "FROM services"
        )

        if not include_inactive:
            query += " WHERE is_active=1"

        query += " ORDER BY name"

        async with self._db.connect() as db:
            cursor = await db.execute(query)
            rows = await cursor.fetchall()
            return [_service_from_row(row) for row in rows]

    async def get(self, service_id: str) -> Service | None:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "SELECT id,name,description,price_cents,duration_minutes,is_active "
                "FROM services WHERE id=?",
                (service_id,),
            )
            row = await cursor.fetchone()
            return _service_from_row(row) if row else None

    async def create(
        self,
        name: str,
        description: str,
        price_cents: int,
        duration_minutes: int,
    ) -> Service:
        service = Service(
            str(uuid4()),
            name,
            description,
            price_cents,
            duration_minutes,
        )

        await self._db.execute(
            "INSERT INTO services("
            "id,name,description,price_cents,duration_minutes,is_active"
            ") VALUES(?,?,?,?,?,1)",
            (
                service.id,
                service.name,
                service.description,
                service.price_cents,
                service.duration_minutes,
            ),
        )

        return service

    async def update(
        self,
        service_id: str,
        *,
        name: str,
        description: str,
        price_cents: int,
        duration_minutes: int,
        is_active: bool,
    ) -> Service | None:
        if await self.get(service_id) is None:
            return None

        await self._db.execute(
            "UPDATE services SET name=?,description=?,price_cents=?,"
            "duration_minutes=?,is_active=? WHERE id=?",
            (
                name,
                description,
                price_cents,
                duration_minutes,
                int(is_active),
                service_id,
            ),
        )

        return Service(
            service_id,
            name,
            description,
            price_cents,
            duration_minutes,
            is_active,
        )

    async def delete(self, service_id: str) -> bool:
        async with self._db.connect() as db:
            cursor = await db.execute(
                "UPDATE services SET is_active=0 WHERE id=?",
                (service_id,),
            )
            await db.commit()
            return cursor.rowcount > 0


def _user_from_row(row: Any) -> User:
    return User(
        row["id"],
        row["email"],
        row["password_hash"],
        bool(row["is_active"]),
        Role(row["role"]),
    )


def _appointment_from_row(row: Any) -> Appointment:
    return Appointment(
        row["id"],
        row["barber_id"],
        _parse_dt(row["starts_at"]),
        _parse_dt(row["ends_at"]),
        row["client_id"],
        row["service_id"],
    )


def _service_from_row(row: Any) -> Service:
    return Service(
        row["id"],
        row["name"],
        row["description"],
        int(row["price_cents"]),
        int(row["duration_minutes"]),
        bool(row["is_active"]),
    )


def _dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)

    return parsed