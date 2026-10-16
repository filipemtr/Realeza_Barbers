import asyncio
import hashlib
import unittest
from datetime import datetime, timedelta, timezone

import httpx

from app.audit import AuditEvent
from app.auth import (
    Role,
    SESSION_COOKIE,
    StoredSession,
    User,
    create_auth_app,
    hash_password,
    verify_password,
)


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


class AuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.user = User(
            id="user-1",
            email="barbeiro@example.com",
            password_hash=hash_password("senha-segura"),
        )
        self.users = FakeUserRepository(self.user)
        self.sessions = FakeSessionRepository()
        self.audit = FakeAuditRepository()
        self.app = create_auth_app(
            self.users, self.sessions, self.audit, cookie_secure=False
        )

    def _async_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app),
            base_url="http://testserver",
        )

    def test_password_is_hashed_and_verified(self) -> None:
        password_hash = hash_password("senha-segura")

        self.assertNotEqual(password_hash, "senha-segura")
        self.assertTrue(verify_password("senha-segura", password_hash))
        self.assertFalse(verify_password("senha-errada", password_hash))
        self.assertFalse(verify_password("á" * 37, password_hash))

    def test_login_creates_hashed_server_side_session(self) -> None:
        async def scenario() -> None:
            async with self._async_client() as client:
                response = await client.post(
                    "/auth/login",
                    json={"email": "barbeiro@example.com", "password": "senha-segura"},
                )

                self.assertEqual(response.status_code, 200)
                cookie = response.cookies[SESSION_COOKIE]
                token_hash = hashlib.sha256(cookie.encode("ascii")).hexdigest()
                self.assertNotEqual(token_hash, cookie)
                self.assertIn(token_hash, self.sessions.sessions)
                self.assertIn("HttpOnly", response.headers["set-cookie"])
                self.assertIn("SameSite=lax", response.headers["set-cookie"])
                self.assertEqual(self.audit.events[-1].action, "auth.login.succeeded")

        asyncio.run(scenario())

    def test_invalid_credentials_have_same_response(self) -> None:
        async def scenario() -> None:
            async with self._async_client() as client:
                for credentials in (
                    {"email": "barbeiro@example.com", "password": "errada"},
                    {"email": "desconhecido@example.com", "password": "errada"},
                ):
                    with self.subTest(email=credentials["email"]):
                        response = await client.post(
                            "/auth/login", json=credentials
                        )
                        self.assertEqual(response.status_code, 401)
                        self.assertEqual(
                            response.json()["detail"],
                            "Usuário ou senha inválidos",
                        )
                self.assertEqual(
                    [event.action for event in self.audit.events],
                    ["auth.login.failed", "auth.login.failed"],
                )
                self.assertIsNone(self.audit.events[1].actor_user_id)
                self.assertEqual(
                    self.audit.events[1].details["email"],
                    "desconhecido@example.com",
                )
                self.assertEqual(
                    self.audit.events[1].occurred_at.utcoffset(), timedelta(0)
                )

        asyncio.run(scenario())

    def test_session_protects_me_and_logout_revokes_it(self) -> None:
        async def scenario() -> None:
            async with self._async_client() as client:
                await client.post(
                    "/auth/login",
                    json={"email": "barbeiro@example.com", "password": "senha-segura"},
                )

                me_response = await client.get("/auth/me")
                self.assertEqual(me_response.status_code, 200)
                self.assertEqual(
                    me_response.json(),
                    {
                        "id": "user-1",
                        "email": "barbeiro@example.com",
                        "role": Role.USER.value,
                    },
                )

                logout_response = await client.post("/auth/logout")
                self.assertEqual(logout_response.status_code, 204)
                self.assertEqual(self.sessions.sessions, {})
                self.assertEqual(self.audit.events[-1].action, "auth.logout")
                self.assertEqual((await client.get("/auth/me")).status_code, 401)

        asyncio.run(scenario())

    def test_expired_session_is_revoked(self) -> None:
        token = "expired-token"
        token_hash = hashlib.sha256(token.encode("ascii")).hexdigest()
        self.sessions.sessions[token_hash] = StoredSession(
            self.user.id, datetime.now(timezone.utc) - timedelta(seconds=1)
        )
        async def scenario() -> None:
            async with self._async_client() as client:
                client.cookies.set(SESSION_COOKIE, token)
                response = await client.get("/auth/me")

                self.assertEqual(response.status_code, 401)
                self.assertNotIn(token_hash, self.sessions.sessions)
                expired_event = self.audit.events[-1]
                self.assertEqual(expired_event.action, "auth.session.expired")
                self.assertEqual(expired_event.actor_user_id, self.user.id)
                self.assertEqual(expired_event.occurred_at.utcoffset(), timedelta(0))

        asyncio.run(scenario())

    def test_missing_and_invalid_sessions_are_audited_without_token(self) -> None:
        async def scenario() -> None:
            async with self._async_client() as client:
                missing = await client.get("/auth/me")
                client.cookies.set(SESSION_COOKIE, "unknown-session")
                invalid = await client.get("/auth/me")

                self.assertEqual(missing.status_code, 401)
                self.assertEqual(invalid.status_code, 401)
                self.assertEqual(
                    [event.action for event in self.audit.events],
                    ["auth.session.rejected", "auth.session.rejected"],
                )
                self.assertEqual(
                    self.audit.events[0].details["reason"], "missing_session"
                )
                self.assertEqual(
                    self.audit.events[1].details["reason"], "invalid_session"
                )
                for event in self.audit.events:
                    self.assertIsNone(event.actor_user_id)
                    self.assertNotIn("unknown-session", str(event.details))

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
