from __future__ import annotations

import asyncio
import os

from app.auth import Role, hash_password
from app.database import Database, SQLiteServiceRepository, SQLiteUserRepository


async def main() -> None:
    db = Database(os.getenv("REALEZA_DB_PATH", "data/realeza.db"))
    users = SQLiteUserRepository(db)
    services = SQLiteServiceRepository(db)

    demo_accounts = [
        (os.getenv("REALEZA_CLIENT_EMAIL", "cliente@realeza.local"), os.getenv("REALEZA_CLIENT_PASSWORD", "Cliente123!"), Role.USER, "Cliente"),
        (os.getenv("REALEZA_BARBER_EMAIL", "barbeiro@realeza.local"), os.getenv("REALEZA_BARBER_PASSWORD", "Barbeiro123!"), Role.BARBER, "Barbeiro"),
        (os.getenv("REALEZA_ADMIN_EMAIL", "admin@realeza.local"), os.getenv("REALEZA_ADMIN_PASSWORD", "Admin123!"), Role.ADMIN, "Administrador"),
    ]
    for email, password, role, label in demo_accounts:
        if not await users.find_by_email(email):
            await users.create(email, hash_password(password), role)
            print(f"{label} criado: {email}")
        else:
            print(f"{label} já existe: {email}")

    defaults = [
        ("Corte", "Corte masculino tradicional.", 3000, 30),
        ("Barba", "Barba completa.", 2000, 20),
        ("Combo", "Corte + barba.", 4500, 50),
    ]
    existing = {service.name.lower() for service in await services.list(include_inactive=True)}
    for name, description, price, duration in defaults:
        if name.lower() not in existing:
            await services.create(name, description, price, duration)
            print(f"Serviço criado: {name}")


if __name__ == "__main__":
    asyncio.run(main())
