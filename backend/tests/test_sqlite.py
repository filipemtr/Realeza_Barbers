import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from app.auth import Role, hash_password
from app.bookings import AppointmentConflictError
from app.database import (
    Database,
    SQLiteAppointmentRepository,
    SQLiteServiceRepository,
    SQLiteUserRepository,
)


class SQLiteRepositoryTests(unittest.TestCase):
    def test_crud_and_service_relation_are_persisted(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                db = Database(f"{directory}/realeza.db")
                users = SQLiteUserRepository(db)
                services = SQLiteServiceRepository(db)
                appointments = SQLiteAppointmentRepository(db)

                barber = await users.create("barber@example.com", hash_password("password"), Role.BARBER)
                client = await users.create("client@example.com", hash_password("password"), Role.USER)
                service = await services.create("Corte", "Corte tradicional", 3000, 30)

                start = datetime.now(timezone.utc) + timedelta(days=1)
                created = await appointments.create(
                    barber.id,
                    start,
                    start + timedelta(minutes=30),
                    client_id=client.id,
                    service_id=service.id,
                )

                loaded = await appointments.get_by_id(created.id)
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.service_id, service.id)
                self.assertEqual((await appointments.list_for_client(client.id))[0].service_id, service.id)

                with self.assertRaises(AppointmentConflictError):
                    await appointments.create(
                        barber.id,
                        start + timedelta(minutes=15),
                        start + timedelta(minutes=45),
                    )

                updated = await appointments.update(
                    created.id,
                    barber.id,
                    start + timedelta(hours=1),
                    start + timedelta(hours=1, minutes=30),
                )
                self.assertEqual(updated.service_id, service.id)
                self.assertTrue(await appointments.delete(created.id))
                self.assertIsNone(await appointments.get_by_id(created.id))

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
