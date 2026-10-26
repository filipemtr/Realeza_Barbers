import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from app.application import create_app
from app.auth import Role, StoredSession, User, hash_password
from app.database import Database, SQLiteAppointmentRepository, SQLiteServiceRepository, SQLiteUserRepository
from app.audit import AuditEvent


class FakeSessionRepository:
    def __init__(self): self.sessions = {}
    async def create(self, token_hash, user_id, expires_at): self.sessions[token_hash] = StoredSession(user_id, expires_at)
    async def find_by_token_hash(self, token_hash): return self.sessions.get(token_hash)
    async def delete_by_token_hash(self, token_hash): self.sessions.pop(token_hash, None)
    async def delete_for_user(self, user_id):
        self.sessions = {key: value for key, value in self.sessions.items() if value.user_id != user_id}


class FakeAuditRepository:
    def __init__(self): self.events = []
    async def record(self, event: AuditEvent): self.events.append(event)


class ResourceApiTests(unittest.TestCase):
    def test_services_are_public_and_admin_can_manage_users_and_services(self):
        async def scenario():
            with tempfile.TemporaryDirectory() as directory:
                db = Database(f"{directory}/realeza.db")
                users = SQLiteUserRepository(db)
                services = SQLiteServiceRepository(db)
                appointments = SQLiteAppointmentRepository(db)
                sessions = FakeSessionRepository()
                audit = FakeAuditRepository()
                admin = await users.create("admin@example.com", hash_password("password"), Role.ADMIN)
                app = create_app(
                    user_repository=users,
                    session_repository=sessions,
                    appointment_repository=appointments,
                    audit_repository=audit,
                    service_repository=services,
                    cookie_secure=False,
                    audit_log_path=__import__("pathlib").Path(directory) / "audit.jsonl",
                )
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
                    public_services = await client.get("/services")
                    self.assertEqual(public_services.status_code, 200)
                    self.assertEqual(public_services.json(), [])
                    login = await client.post("/auth/login", json={"email": admin.email, "password": "password"})
                    self.assertEqual(login.status_code, 200)
                    created_service = await client.post("/services", json={"name": "Corte", "description": "", "price_cents": 3000, "duration_minutes": 30, "is_active": True})
                    self.assertEqual(created_service.status_code, 201)
                    # Senhas que ultrapassam o limite real em bytes devem gerar 422,
                    # nunca um erro 500 do bcrypt.
                    too_long_password = await client.post("/admin/users", json={"email": "longpass@example.com", "password": "á" * 40, "role": "user", "is_active": True})
                    self.assertEqual(too_long_password.status_code, 422)

                    created_user = await client.post("/admin/users", json={"email": " Barber@Example.com ", "password": "password", "role": "barber", "is_active": True})
                    self.assertEqual(created_user.status_code, 201)
                    self.assertEqual(created_user.json()["email"], "barber@example.com")
                    sessions.sessions["test-token-hash"] = StoredSession(created_user.json()["id"], datetime.now(timezone.utc) + timedelta(hours=1))
                    updated_user = await client.put(f"/admin/users/{created_user.json()['id']}", json={"is_active": False})
                    self.assertEqual(updated_user.status_code, 200)
                    self.assertFalse(any(item.user_id == created_user.json()["id"] for item in sessions.sessions.values()))

                    self_deactivate = await client.put(f"/admin/users/{admin.id}", json={"is_active": False})
                    self.assertEqual(self_deactivate.status_code, 400)
                    deleted_service = await client.delete(f"/services/{created_service.json()['id']}")
                    self.assertEqual(deleted_service.status_code, 204)
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
