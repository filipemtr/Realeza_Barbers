import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class AuditEvent:
    """registro imutável de quem fez o quê e quando."""

    actor_user_id: str | None
    action: str
    occurred_at: datetime
    details: dict[str, str | None]


class AuditRepository(Protocol):
    """contrato para o adaptador de auditoria que será ligado ao banco."""

    # O adaptador SQLite grava os eventos em audit_logs.
    async def record(self, event: AuditEvent) -> None: ...


class JsonlAuditRepository:
    """Persiste cada evento em uma linha JSON para inspeção e backup local."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()

    async def record(self, event: AuditEvent) -> None:
        record = {
            "actor_user_id": event.actor_user_id,
            "action": event.action,
            "occurred_at": event.occurred_at.isoformat(),
            "details": event.details,
        }
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        async with self._lock:
            await asyncio.to_thread(self._append_line, line)

    def _append_line(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(f"{line}\n")


class CompositeAuditRepository:
    """Grava cada evento em todos os repositórios configurados."""

    def __init__(self, *repositories: AuditRepository) -> None:
        self.repositories = repositories

    async def record(self, event: AuditEvent) -> None:
        for repository in self.repositories:
            await repository.record(event)


async def record_event(
    repository: AuditRepository,
    *,
    actor_user_id: str | None,
    action: str,
    details: dict[str, str | None],
) -> None:
    """registra evento com instante UTC, as falhas do repositório não são ocultadas."""
    await repository.record(
        AuditEvent(
            actor_user_id=actor_user_id,
            action=action,
            occurred_at=datetime.now(timezone.utc),
            details=details,
        )
    )
