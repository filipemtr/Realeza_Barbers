import asyncio
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.audit import AuditEvent
from app.application import create_app
from app.auth import Role, SESSION_COOKIE, StoredSession, User, hash_password
from app.bookings import Appointment


class FakeUserRepository:
    def __init__(self, *users: User) -> None:
        self.users = {user.id: user for user in users}

    async def find_by_email(self, email: str) -> User | None:
        return next((user for user in self.users.values() if user.email == email), None)

    async def find_by_id(self, user_id: str) -> User | None:
        return self.users.get(user_id)


class FakeSessionRepository:
    def __init__(self) -> None:
        self.sessions: dict[str, StoredSession] = {}

    async def create(
        self, token_hash: str, user_id: str, expires_at: datetime
    ) -> None:
        self.sessions[token_hash] = StoredSession(user_id, expires_at)

    async def find_by_token_hash(self, token_hash: str) -> StoredSession | None:
        return self.sessions.get(token_hash)

    async def delete_by_token_hash(self, token_hash: str) -> None:
        self.sessions.pop(token_hash, None)


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


class FakeAppointmentRepository:
    """Memória de teste apenas: o adaptador de produção fica para o CRUD do banco."""

    def __init__(self) -> None:
        self.appointments: dict[str, Appointment] = {}
        self.next_id = 1

    async def list_for_barber(self, barber_id: str | None) -> list[Appointment]:
        return [
            item
            for item in self.appointments.values()
            if barber_id is None or item.barber_id == barber_id
        ]

    async def list_for_client(self, client_id: str) -> list[Appointment]:
        return [
            item
            for item in self.appointments.values()
            if item.client_id == client_id
        ]

    async def get_by_id(self, appointment_id: str) -> Appointment | None:
        return self.appointments.get(appointment_id)

    async def has_conflict(
        self,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        excluding_id: str | None = None,
    ) -> bool:
        return any(
            item.id != excluding_id
            and item.barber_id == barber_id
            and item.starts_at < ends_at
            and item.ends_at > starts_at
            for item in self.appointments.values()
        )

    async def create(
        self,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        client_id: str | None = None,
    ) -> Appointment:
        item = Appointment(
            str(self.next_id), barber_id, starts_at, ends_at, client_id
        )
        self.next_id += 1
        self.appointments[item.id] = item
        return item

    async def update(
        self,
        appointment_id: str,
        barber_id: str,
        starts_at: datetime,
        ends_at: datetime,
    ) -> Appointment | None:
        if appointment_id not in self.appointments:
            return None
        existing = self.appointments[appointment_id]
        item = Appointment(
            appointment_id,
            barber_id,
            starts_at,
            ends_at,
            existing.client_id,
        )
        self.appointments[appointment_id] = item
        return item

    async def delete(self, appointment_id: str) -> bool:
        return self.appointments.pop(appointment_id, None) is not None


class BookingApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.barber = User(
            "barber-1",
            "barbeiro@example.com",
            hash_password("senha"),
            role=Role.BARBER,
        )
        self.other_barber = User(
            "barber-2",
            "outro@example.com",
            hash_password("senha"),
            role=Role.BARBER,
        )
        self.admin = User(
            "admin-1",
            "admin@example.com",
            hash_password("senha"),
            role=Role.ADMIN,
        )
        self.customer = User(
            "customer-1",
            "cliente@example.com",
            hash_password("senha"),
        )
        self.users = FakeUserRepository(
            self.barber, self.other_barber, self.admin, self.customer
        )
        self.sessions = FakeSessionRepository()
        self.audit = FakeAuditRepository()
        self.appointments = FakeAppointmentRepository()
        self.audit_log_directory = tempfile.TemporaryDirectory()
        self.audit_log_path = Path(self.audit_log_directory.name) / "audit.jsonl"
        self.app = create_app(
            user_repository=self.users,
            session_repository=self.sessions,
            appointment_repository=self.appointments,
            audit_repository=self.audit,
            cookie_secure=False,
            audit_log_path=self.audit_log_path,
        )

    def tearDown(self) -> None:
        self.audit_log_directory.cleanup()

    def _payload(
        self, *, start_delta: timedelta = timedelta(days=1), barber_id: str | None = None
    ) -> dict[str, str | bool]:
        starts_at = datetime.now(timezone.utc) + start_delta
        ends_at = starts_at + timedelta(minutes=30)
        data = {
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "confirmed": True,
        }
        if barber_id is not None:
            data["barber_id"] = barber_id
        return data

    async def _login(self, client: httpx.AsyncClient, user: User) -> None:
        response = await client.post(
            "/auth/login",
            json={"email": user.email, "password": "senha"},
        )
        self.assertEqual(response.status_code, 200)

    def test_barber_can_create_and_manage_only_own_appointments(self) -> None:
        async def scenario() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.barber)
                created = await client.post("/appointments", json=self._payload())
                self.assertEqual(created.status_code, 201)
                self.assertEqual(created.json()["barber_id"], self.barber.id)
                appointment_id = created.json()["id"]

                attempted_transfer = await client.post(
                    "/appointments",
                    json=self._payload(barber_id=self.other_barber.id),
                )
                self.assertEqual(attempted_transfer.status_code, 403)

                forbidden_update = await client.put(
                    f"/appointments/{appointment_id}",
                    json=self._payload(
                        barber_id=self.other_barber.id
                    ),
                )
                self.assertEqual(forbidden_update.status_code, 403)
                self.assertEqual(
                    [event.action for event in self.audit.events],
                    [
                        "auth.login.succeeded",
                        "appointment.created",
                        "authorization.denied",
                        "authorization.denied",
                    ],
                )

        asyncio.run(scenario())

    def test_barber_cannot_read_update_or_delete_another_barbers_booking(self) -> None:
        async def scenario() -> None:
            other_booking = await self.appointments.create(
                self.other_barber.id,
                datetime.now(timezone.utc) + timedelta(days=1),
                datetime.now(timezone.utc) + timedelta(days=1, minutes=30),
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.barber)
                listing = await client.get("/appointments")
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(listing.json(), [])

                update = await client.put(
                    f"/appointments/{other_booking.id}",
                    json=self._payload(),
                )
                delete = await client.request(
                    "DELETE",
                    f"/appointments/{other_booking.id}",
                    json={"confirmed": True},
                )
                self.assertEqual(update.status_code, 403)
                self.assertEqual(delete.status_code, 403)
                self.assertIn(other_booking.id, self.appointments.appointments)
                denied_events = [
                    event
                    for event in self.audit.events
                    if event.action == "authorization.denied"
                ]
                self.assertEqual(len(denied_events), 2)
                self.assertEqual(denied_events[0].actor_user_id, self.barber.id)
                self.assertEqual(
                    denied_events[0].details["appointment_id"],
                    other_booking.id,
                )

        asyncio.run(scenario())

    def test_admin_can_create_for_any_barber_and_manage_all_bookings(self) -> None:
        async def scenario() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.admin)
                created = await client.post(
                    "/appointments",
                    json=self._payload(barber_id=self.barber.id),
                )
                self.assertEqual(created.status_code, 201)
                appointment_id = created.json()["id"]

                listing = await client.get("/appointments")
                self.assertEqual(len(listing.json()), 1)

                updated = await client.put(
                    f"/appointments/{appointment_id}",
                    json=self._payload(
                        start_delta=timedelta(days=2),
                        barber_id=self.other_barber.id,
                    ),
                )
                self.assertEqual(updated.status_code, 200)
                self.assertEqual(updated.json()["barber_id"], self.other_barber.id)

                deleted = await client.request(
                    "DELETE",
                    f"/appointments/{appointment_id}",
                    json={"confirmed": True},
                )
                self.assertEqual(deleted.status_code, 204)
                self.assertNotIn(appointment_id, self.appointments.appointments)
                self.assertEqual(
                    [event.action for event in self.audit.events],
                    [
                        "auth.login.succeeded",
                        "appointment.created",
                        "appointments.listed",
                        "appointment.updated",
                        "appointment.deleted",
                    ],
                )
                self.assertEqual(self.audit.events[-1].actor_user_id, self.admin.id)
                self.assertEqual(
                    self.audit.events[-1].occurred_at.utcoffset(), timedelta(0)
                )

        asyncio.run(scenario())

    def test_customer_can_view_reschedule_and_cancel_own_appointments(self) -> None:
        async def scenario() -> None:
            other_customer = User(
                "customer-2",
                "outro-cliente@example.com",
                hash_password("senha"),
            )
            self.users.users[other_customer.id] = other_customer
            occupied_start = datetime.now(timezone.utc) + timedelta(days=3)
            await self.appointments.create(
                self.barber.id,
                occupied_start,
                occupied_start + timedelta(minutes=30),
                client_id=other_customer.id,
            )
            await self.appointments.create(
                self.other_barber.id,
                occupied_start,
                occupied_start + timedelta(minutes=30),
                client_id=other_customer.id,
            )
            near_start = datetime.now(timezone.utc) + timedelta(minutes=90)
            near_appointment = await self.appointments.create(
                self.barber.id,
                near_start,
                near_start + timedelta(minutes=30),
                client_id=self.customer.id,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.customer)
                created = await client.post(
                    "/appointments",
                    json=self._payload(barber_id=self.barber.id),
                )
                self.assertEqual(created.status_code, 201)
                appointment_id = created.json()["id"]
                self.assertEqual(created.json()["barber_id"], self.barber.id)
                self.assertEqual(created.json()["client_id"], self.customer.id)

                listing = await client.get("/appointments")
                self.assertEqual(listing.status_code, 200)
                self.assertEqual(
                    {item["id"] for item in listing.json()},
                    {appointment_id, near_appointment.id},
                )

                unavailable = await client.put(
                    f"/appointments/{appointment_id}",
                    json={
                        "starts_at": occupied_start.isoformat(),
                        "ends_at": (
                            occupied_start + timedelta(minutes=30)
                        ).isoformat(),
                        "confirmed": True,
                    },
                )
                self.assertEqual(unavailable.status_code, 409)

                reschedule_payload = self._payload(start_delta=timedelta(days=2))
                rescheduled = await client.put(
                    f"/appointments/{appointment_id}",
                    json=reschedule_payload,
                )
                self.assertEqual(rescheduled.status_code, 200)
                self.assertEqual(
                    datetime.fromisoformat(rescheduled.json()["starts_at"]),
                    datetime.fromisoformat(reschedule_payload["starts_at"]),
                )
                self.assertEqual(rescheduled.json()["client_id"], self.customer.id)

                unavailable_barber = await client.put(
                    f"/appointments/{appointment_id}",
                    json={
                        "barber_id": self.other_barber.id,
                        "starts_at": occupied_start.isoformat(),
                        "ends_at": (
                            occupied_start + timedelta(minutes=30)
                        ).isoformat(),
                        "confirmed": True,
                    },
                )
                self.assertEqual(unavailable_barber.status_code, 409)
                switch_payload = self._payload(
                    start_delta=timedelta(days=2),
                    barber_id=self.other_barber.id,
                )
                switched = await client.put(
                    f"/appointments/{appointment_id}", json=switch_payload
                )
                self.assertEqual(switched.status_code, 200)
                self.assertEqual(switched.json()["barber_id"], self.other_barber.id)

                late_update = await client.put(
                    f"/appointments/{near_appointment.id}",
                    json=self._payload(start_delta=timedelta(days=4)),
                )
                late_cancel = await client.request(
                    "DELETE",
                    f"/appointments/{near_appointment.id}",
                    json={"confirmed": True},
                )
                self.assertEqual(late_update.status_code, 403)
                self.assertEqual(late_cancel.status_code, 403)
                self.assertIn(
                    near_appointment.id, self.appointments.appointments
                )

                # Another customer cannot view or change this appointment.
                client.cookies.clear()
                await self._login(client, other_customer)
                other_listing = await client.get("/appointments")
                forbidden_update = await client.put(
                    f"/appointments/{appointment_id}",
                    json=self._payload(start_delta=timedelta(days=3)),
                )
                forbidden_delete = await client.request(
                    "DELETE",
                    f"/appointments/{appointment_id}",
                    json={"confirmed": True},
                )
                self.assertEqual(
                    {item["client_id"] for item in other_listing.json()},
                    {other_customer.id},
                )
                self.assertEqual(forbidden_update.status_code, 403)
                self.assertEqual(forbidden_delete.status_code, 403)

                client.cookies.clear()
                await self._login(client, self.customer)
                delete = await client.request(
                    "DELETE",
                    f"/appointments/{appointment_id}",
                    json={"confirmed": True},
                )
                self.assertEqual(delete.status_code, 204)
                self.assertNotIn(appointment_id, self.appointments.appointments)

        asyncio.run(scenario())

    def test_audit_log_persists_actor_and_appointment_times(self) -> None:
        async def scenario() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.customer)
                payload = self._payload(barber_id=self.barber.id)
                response = await client.post("/appointments", json=payload)
                self.assertEqual(response.status_code, 201)
                appointment_id = response.json()["id"]
                new_payload = self._payload(
                    start_delta=timedelta(days=2),
                    barber_id=self.barber.id,
                )
                updated = await client.put(
                    f"/appointments/{appointment_id}", json=new_payload
                )
                self.assertEqual(updated.status_code, 200)
                deleted = await client.request(
                    "DELETE",
                    f"/appointments/{appointment_id}",
                    json={"confirmed": True},
                )
                self.assertEqual(deleted.status_code, 204)

                audit_rows = [
                    json.loads(line)
                    for line in self.audit_log_path.read_text(
                        encoding="utf-8"
                    ).splitlines()
                ]
                created_event = next(
                    row
                    for row in audit_rows
                    if row["action"] == "appointment.created"
                )
                self.assertEqual(
                    created_event["actor_user_id"], self.customer.id
                )
                self.assertEqual(
                    datetime.fromisoformat(
                        created_event["details"]["starts_at"]
                    ),
                    datetime.fromisoformat(response.json()["starts_at"]),
                )
                self.assertEqual(
                    datetime.fromisoformat(
                        created_event["details"]["ends_at"]
                    ),
                    datetime.fromisoformat(response.json()["ends_at"]),
                )
                self.assertEqual(
                    created_event["details"]["client_id"], self.customer.id
                )
                updated_event = next(
                    row
                    for row in audit_rows
                    if row["action"] == "appointment.updated"
                )
                self.assertEqual(
                    datetime.fromisoformat(
                        updated_event["details"]["previous_starts_at"]
                    ),
                    datetime.fromisoformat(response.json()["starts_at"]),
                )
                self.assertEqual(
                    datetime.fromisoformat(updated_event["details"]["starts_at"]),
                    datetime.fromisoformat(updated.json()["starts_at"]),
                )
                deleted_event = next(
                    row
                    for row in audit_rows
                    if row["action"] == "appointment.deleted"
                )
                self.assertEqual(deleted_event["actor_user_id"], self.customer.id)
                self.assertEqual(
                    datetime.fromisoformat(deleted_event["details"]["starts_at"]),
                    datetime.fromisoformat(updated.json()["starts_at"]),
                )

        asyncio.run(scenario())

    def test_barber_can_cancel_only_until_two_hours_before(self) -> None:
        async def scenario() -> None:
            starts_at = datetime.now(timezone.utc) + timedelta(minutes=90)
            appointment = await self.appointments.create(
                self.barber.id,
                starts_at,
                starts_at + timedelta(minutes=30),
                client_id=self.customer.id,
            )
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.barber)
                cancellation = await client.request(
                    "DELETE",
                    f"/appointments/{appointment.id}",
                    json={"confirmed": True},
                )
                self.assertEqual(cancellation.status_code, 403)
                self.assertIn(appointment.id, self.appointments.appointments)

        asyncio.run(scenario())

    def test_invalid_role_cannot_manage_appointments(self) -> None:
        async def scenario() -> None:
            appointment = await self.appointments.create(
                self.barber.id,
                datetime.now(timezone.utc) + timedelta(days=1),
                datetime.now(timezone.utc) + timedelta(days=1, minutes=30),
            )
            invalid_user = User(
                "invalid",
                "invalid@example.com",
                "hash",
                role="invalid",  # type: ignore[arg-type]
            )
            self.app.dependency_overrides[
                self.app.state.get_current_user
            ] = lambda: invalid_user
            try:
                async with httpx.AsyncClient(
                    transport=httpx.ASGITransport(app=self.app),
                    base_url="http://testserver",
                ) as client:
                    listing = await client.get("/appointments")
                    update = await client.put(
                        f"/appointments/{appointment.id}",
                        json=self._payload(),
                    )
                    delete = await client.request(
                        "DELETE",
                        f"/appointments/{appointment.id}",
                        json={"confirmed": True},
                    )
                    self.assertEqual(listing.status_code, 403)
                    self.assertEqual(update.status_code, 403)
                    self.assertEqual(delete.status_code, 403)
                    self.assertIn(
                        appointment.id, self.appointments.appointments
                    )
            finally:
                self.app.dependency_overrides.clear()

        asyncio.run(scenario())

    def test_booking_changes_require_explicit_confirmation(self) -> None:
        async def scenario() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.customer)
                unconfirmed_create = await client.post(
                    "/appointments",
                    json={
                        **self._payload(barber_id=self.barber.id),
                        "confirmed": False,
                    },
                )
                missing_confirmation_payload = self._payload(
                    barber_id=self.barber.id
                )
                missing_confirmation_payload.pop("confirmed")
                missing_confirmation = await client.post(
                    "/appointments", json=missing_confirmation_payload
                )
                self.assertEqual(unconfirmed_create.status_code, 422)
                self.assertEqual(missing_confirmation.status_code, 422)
                self.assertEqual(self.appointments.appointments, {})
                rejected_requests = [
                    event
                    for event in self.audit.events
                    if event.action == "request.validation.rejected"
                ]
                self.assertEqual(len(rejected_requests), 2)
                self.assertTrue(
                    all(
                        event.actor_user_id == self.customer.id
                        for event in rejected_requests
                    )
                )

                created = await client.post(
                    "/appointments",
                    json=self._payload(barber_id=self.barber.id),
                )
                appointment_id = created.json()["id"]
                current_start = self.appointments.appointments[
                    appointment_id
                ].starts_at
                unconfirmed_update = await client.put(
                    f"/appointments/{appointment_id}",
                    json={
                        **self._payload(start_delta=timedelta(days=2)),
                        "confirmed": False,
                    },
                )
                unconfirmed_cancel = await client.request(
                    "DELETE",
                    f"/appointments/{appointment_id}",
                    json={"confirmed": False},
                )
                self.assertEqual(unconfirmed_update.status_code, 422)
                self.assertEqual(unconfirmed_cancel.status_code, 422)
                self.assertEqual(
                    self.appointments.appointments[appointment_id].starts_at,
                    current_start,
                )
                self.assertIn(appointment_id, self.appointments.appointments)

        asyncio.run(scenario())

    def test_rejects_past_naive_invalid_and_conflicting_times(self) -> None:
        async def scenario() -> None:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=self.app),
                base_url="http://testserver",
            ) as client:
                await self._login(client, self.barber)
                past = await client.post(
                    "/appointments",
                    json=self._payload(start_delta=timedelta(days=-1)),
                )
                self.assertEqual(past.status_code, 422)

                naive_payload = self._payload()
                naive_payload["starts_at"] = datetime.now().isoformat()
                naive = await client.post("/appointments", json=naive_payload)
                self.assertEqual(naive.status_code, 422)

                invalid_interval = self._payload()
                invalid_interval["ends_at"] = invalid_interval["starts_at"]
                invalid = await client.post("/appointments", json=invalid_interval)
                self.assertEqual(invalid.status_code, 422)

                first_payload = self._payload(start_delta=timedelta(days=3))
                first = await client.post("/appointments", json=first_payload)
                self.assertEqual(first.status_code, 201)
                conflict = await client.post(
                    "/appointments",
                    json={
                        "starts_at": (
                            datetime.fromisoformat(first_payload["starts_at"])
                            + timedelta(minutes=15)
                        ).isoformat(),
                        "ends_at": (
                            datetime.fromisoformat(first_payload["ends_at"])
                            + timedelta(minutes=15)
                        ).isoformat(),
                        "confirmed": True,
                    },
                )
                self.assertEqual(conflict.status_code, 409)

                second = await client.post(
                    "/appointments",
                    json=self._payload(start_delta=timedelta(days=4)),
                )
                self.assertEqual(second.status_code, 201)
                update_conflict = await client.put(
                    f"/appointments/{second.json()['id']}",
                    json={
                        "starts_at": first_payload["starts_at"],
                        "ends_at": first_payload["ends_at"],
                        "confirmed": True,
                    },
                )
                self.assertEqual(update_conflict.status_code, 409)

                # Intervalos adjacentes não se sobrepõem.
                adjacent = await client.post(
                    "/appointments",
                    json={
                        "starts_at": first_payload["ends_at"],
                        "ends_at": (
                            datetime.fromisoformat(first_payload["ends_at"])
                            + timedelta(minutes=30)
                        ).isoformat(),
                        "confirmed": True,
                    },
                )
                self.assertEqual(adjacent.status_code, 201)

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
