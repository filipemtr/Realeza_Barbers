import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.application import create_app
from app.auth import Role, hash_password
from app.database import Database, SQLiteAppointmentRepository, SQLiteAuditRepository, SQLiteServiceRepository, SQLiteSessionRepository, SQLiteUserRepository


class SQLiteApiIntegrationTests(unittest.TestCase):
    def test_login_booking_conflict_list_and_cancel_use_sqlite(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                db = Database(f"{directory}/realeza.db")
                users = SQLiteUserRepository(db)
                sessions = SQLiteSessionRepository(db)
                appointments = SQLiteAppointmentRepository(db)
                services = SQLiteServiceRepository(db)
                audit = SQLiteAuditRepository(db)
                admin = await users.create("admin@example.com", hash_password("password"), Role.ADMIN)
                barber = await users.create("barber@example.com", hash_password("password"), Role.BARBER)
                client = await users.create("client@example.com", hash_password("password"), Role.USER)
                service = await services.create("Corte", "", 3000, 30)
                app = create_app(
                    user_repository=users,
                    session_repository=sessions,
                    appointment_repository=appointments,
                    audit_repository=audit,
                    service_repository=services,
                    cookie_secure=False,
                    audit_log_path=Path(directory) / "audit.jsonl",
                )
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as customer:
                    login = await customer.post("/auth/login", json={"email": client.email, "password": "password"})
                    self.assertEqual(login.status_code, 200)
                    # Os horários públicos são oferecidos em blocos de 30 minutos,
                    # no fuso de funcionamento da barbearia (America/Sao_Paulo).
                    from zoneinfo import ZoneInfo
                    business_tz = ZoneInfo("America/Sao_Paulo")
                    local_future = (datetime.now(business_tz) + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
                    future = local_future.astimezone(timezone.utc)
                    payload = {
                        "barber_id": barber.id,
                        "service_id": service.id,
                        "starts_at": future.isoformat(),
                        "ends_at": (future + timedelta(minutes=30)).isoformat(),
                        "confirmed": True,
                    }
                    created = await customer.post("/appointments", json=payload)
                    self.assertEqual(created.status_code, 201)
                    self.assertEqual(created.json()["service_id"], service.id)
                    conflict = await customer.post("/appointments", json=payload)
                    self.assertEqual(conflict.status_code, 409)

                    # A atualização não pode omitir service_id para burlar a duração
                    # que já está associada ao agendamento.
                    wrong_duration = {
                        "barber_id": barber.id,
                        "starts_at": (future + timedelta(hours=1)).isoformat(),
                        "ends_at": (future + timedelta(hours=1, minutes=45)).isoformat(),
                        "confirmed": True,
                    }
                    duration_response = await customer.put(f"/appointments/{created.json()['id']}", json=wrong_duration)
                    self.assertEqual(duration_response.status_code, 422)

                    # A API também rejeita horários fora do expediente, mesmo se
                    # alguém tentar chamar o endpoint sem usar a tela de horários.
                    from zoneinfo import ZoneInfo
                    closed_start = future.astimezone(ZoneInfo("America/Sao_Paulo")).replace(hour=21, minute=0, second=0, microsecond=0).astimezone(timezone.utc)
                    closed_payload = {
                        "barber_id": barber.id,
                        "service_id": service.id,
                        "starts_at": closed_start.isoformat(),
                        "ends_at": (closed_start + timedelta(minutes=30)).isoformat(),
                        "confirmed": True,
                    }
                    closed_response = await customer.post("/appointments", json=closed_payload)
                    self.assertEqual(closed_response.status_code, 422)

                    listed = await customer.get("/appointments")
                    self.assertEqual(len(listed.json()), 1)
                    cancelled = await customer.request("DELETE", f"/appointments/{created.json()['id']}", json={"confirmed": True})
                    self.assertEqual(cancelled.status_code, 204)
                    remaining = await customer.get("/appointments")
                    self.assertEqual(remaining.status_code, 200)
                    self.assertEqual(remaining.json(), [])
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
