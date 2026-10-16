import unittest

from fastapi import HTTPException

from app.authorization import require_admin
from app.auth import Role, User


class AuthorizationTests(unittest.TestCase):
    def test_admin_passes_admin_guard(self) -> None:
        admin = User("admin", "admin@example.com", "hash", role=Role.ADMIN)
        self.assertIs(require_admin(admin), admin)

    def test_barber_is_forbidden_from_admin_guard(self) -> None:
        barber = User("barber", "barber@example.com", "hash", role=Role.BARBER)
        with self.assertRaises(HTTPException) as error:
            require_admin(barber)
        self.assertEqual(error.exception.status_code, 403)

    def test_customer_is_forbidden_from_admin_guard(self) -> None:
        customer = User("customer", "customer@example.com", "hash", role=Role.USER)
        with self.assertRaises(HTTPException) as error:
            require_admin(customer)
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
