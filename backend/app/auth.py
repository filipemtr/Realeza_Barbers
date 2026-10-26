from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Protocol

import bcrypt
from fastapi import Cookie, Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, field_validator
from starlette.responses import JSONResponse

from app.audit import AuditRepository, record_event

SESSION_COOKIE = "barbearia_session"
SESSION_TTL = timedelta(hours=8)
BCRYPT_ROUNDS = 12
# bcrypt processa no máximo 72 bytes; contar os bytes evita cortar caracteres UTF-8.
MAX_PASSWORD_BYTES = 72
# Uma resposta única não revela se o nome de usuário existe.
INVALID_CREDENTIALS = "Usuário ou senha inválidos"


class Role(str, Enum):
    """Perfis disponíveis para clientes, barbeiros e administradores."""

    USER = "user"
    ADMIN = "admin"
    BARBER = "barber"


@dataclass(frozen=True)
class User:
    """Dados mínimos do usuário necessários às regras de autenticação."""

    id: str
    email: str
    password_hash: str
    is_active: bool = True
    role: Role = Role.USER


@dataclass(frozen=True)
class StoredSession:
    """Sessão armazenada, associada ao usuário e ao instante de expiração."""

    user_id: str
    expires_at: datetime


class UserRepository(Protocol):
    """Contrato para buscar usuários sem acoplar autenticação ao ORM."""

    async def find_by_email(self, email: str) -> User | None: ...

    async def find_by_id(self, user_id: str) -> User | None: ...

    async def create(
        self, email: str, password_hash: str, role: Role = Role.USER, *, is_active: bool = True
    ) -> User: ...


class SessionRepository(Protocol):
    """Contrato para persistir, consultar e revogar sessões."""

    async def create(
        self, token_hash: str, user_id: str, expires_at: datetime
    ) -> None: ...

    async def find_by_token_hash(self, token_hash: str) -> StoredSession | None: ...

    async def delete_by_token_hash(self, token_hash: str) -> None: ...

    async def delete_for_user(self, user_id: str) -> None: ...


class LoginRequest(BaseModel):
    """Valida os campos recebidos no corpo da requisição de login."""

    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Informe um e-mail válido")
        return email


class RegisterRequest(BaseModel):
    """Dados para cadastro público; o perfil é sempre cliente."""

    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=8, max_length=72)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Informe um e-mail válido")
        return email


def hash_password(password: str) -> str:
    """Gera hash para armazenar."""
    encoded_password = password.encode("utf-8")
    if len(encoded_password) > MAX_PASSWORD_BYTES:
        raise ValueError("A senha não pode exceder 72 bytes em UTF-8")
    # gensalt cria um pedaço de dado aleatório. aumenta o trabalho
    # necessário para testar cada senha em um eventual vazamento de hashes.
    return bcrypt.hashpw(
        encoded_password, bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Compara uma senha informada com um hash que já foi armazenado."""
    encoded_password = password.encode("utf-8")
    if len(encoded_password) > MAX_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(encoded_password, password_hash.encode("ascii"))


def _hash_session_token(token: str) -> str:
    """Transforma o token aleatório em chave segura para persistência."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_auth_app(
    user_repository: UserRepository,
    session_repository: SessionRepository,
    audit_repository: AuditRepository,
    *,
    cookie_secure: bool = True,
    session_ttl: timedelta = SESSION_TTL,
) -> FastAPI:
    """Cria as rotas de autenticação usando adaptadores de repositório externos."""
    if session_ttl <= timedelta(0):
        raise ValueError("session_ttl deve ser maior que zero")

    app = FastAPI(title="Realeza Barbers API")
    # Usado para executar bcrypt também quando o usuário não existe, reduzindo
    # diferenças de tempo que poderiam ajudar a enumerar contas cadastradas.
    dummy_password_hash = hash_password(secrets.token_urlsafe(32))

    @app.exception_handler(RequestValidationError)
    async def log_invalid_request(
        request: Request, error: RequestValidationError
    ) -> JSONResponse:
        session_token = request.cookies.get(SESSION_COOKIE)
        actor_user_id = None
        if session_token is not None:
            stored_session = await session_repository.find_by_token_hash(
                _hash_session_token(session_token)
            )
            if (
                stored_session is not None
                and stored_session.expires_at.tzinfo is not None
                and stored_session.expires_at.utcoffset() is not None
                and stored_session.expires_at > datetime.now(timezone.utc)
            ):
                user = await user_repository.find_by_id(stored_session.user_id)
                if user is not None and user.is_active:
                    actor_user_id = user.id

        await record_event(
            audit_repository,
            actor_user_id=actor_user_id,
            action="request.validation.rejected",
            details={
                "method": request.method,
                "path": request.url.path,
                "error_count": str(len(error.errors())),
            },
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=jsonable_encoder({"detail": error.errors()}),
        )

    def clear_session_cookie(response: Response) -> None:
        """Instrui o navegador a remover o cookie com os mesmos atributos."""
        response.delete_cookie(
            key=SESSION_COOKIE,
            path="/",
            secure=cookie_secure,
            httponly=True,
            samesite="lax",
        )

    async def get_current_user(
        request: Request,
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> User:
        """valida cookie, sessão, validade e estado da conta para rotas protegidas."""
        if session_token is None:
            await record_event(
                audit_repository,
                actor_user_id=None,
                action="auth.session.rejected",
                details={
                    "reason": "missing_session",
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão não encontrada",
            )

        # So o hash do token é usado na busca, o valor recebido no cookie não
        # precisa ser armazenado diretamente no banco.
        token_hash = _hash_session_token(session_token)
        stored_session = await session_repository.find_by_token_hash(token_hash)
        if stored_session is None:
            await record_event(
                audit_repository,
                actor_user_id=None,
                action="auth.session.rejected",
                details={
                    "reason": "invalid_session",
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão inválida",
            )

        # Datas sem fuso horario podem ser comparadas incorretamente com UTC.
        if (
            stored_session.expires_at.tzinfo is None
            or stored_session.expires_at.utcoffset() is None
        ):
            raise ValueError("expires_at da sessão deve incluir fuso horário")

        if stored_session.expires_at <= datetime.now(timezone.utc):
            await session_repository.delete_by_token_hash(token_hash)
            await record_event(
                audit_repository,
                actor_user_id=stored_session.user_id,
                action="auth.session.expired",
                details={
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão expirada",
            )

        user = await user_repository.find_by_id(stored_session.user_id)
        if user is None or not user.is_active:
            await session_repository.delete_by_token_hash(token_hash)
            await record_event(
                audit_repository,
                actor_user_id=stored_session.user_id,
                action="auth.session.rejected",
                details={
                    "reason": "account_missing_or_inactive",
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão inválida",
            )
        return user

    # A fábrica integrada usa a mesma dependência de sessão nas rotas de negócio.
    app.state.get_current_user = get_current_user

    @app.post("/auth/register", status_code=status.HTTP_201_CREATED)
    async def register(payload: RegisterRequest) -> dict[str, str]:
        """Cria uma conta de cliente. Perfis privilegiados só são criados por admin/seed."""
        email = payload.email.strip().lower()
        if "@" not in email or email.startswith("@") or email.endswith("@"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Informe um e-mail válido.",
            )
        if await user_repository.find_by_email(email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma conta cadastrada com esse e-mail.",
            )
        try:
            password_hash = await asyncio.to_thread(hash_password, payload.password)
        except ValueError as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(error),
            ) from error
        try:
            user = await user_repository.create(email, password_hash, Role.USER)
        except sqlite3.IntegrityError as error:
            # Outra requisição pode cadastrar o mesmo e-mail entre a busca e o INSERT.
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma conta cadastrada com esse e-mail.",
            ) from error
        await record_event(
            audit_repository,
            actor_user_id=user.id,
            action="auth.register.succeeded",
            details={"email": user.email, "role": user.role.value},
        )
        return {"message": "Conta criada com sucesso. Agora você já pode entrar."}

    @app.post("/auth/login")
    async def login(
        payload: LoginRequest,
        response: Response,
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> dict[str, str]:
        """autentica as credenciais e inicia uma sessão nova no servidor."""
        user = await user_repository.find_by_email(payload.email)
        # Mantém o fluxo bcrypt mesmo para senhas grandes, que bcrypt rejeitaria.
        password_to_check = (
            payload.password
            if len(payload.password.encode("utf-8")) <= MAX_PASSWORD_BYTES
            else "senha-invalida"
        )
        # Para usuário inexistente (ou senha grande), compara contra hash fictício.
        stored_hash = (
            user.password_hash
            if user is not None
            and len(payload.password.encode("utf-8")) <= MAX_PASSWORD_BYTES
            else dummy_password_hash
        )
        # bcrypt é deliberadamente custoso; movê-lo evita bloquear o event loop.
        password_matches = await asyncio.to_thread(
            verify_password, password_to_check, stored_hash
        )

        if user is None or not user.is_active or not password_matches:
            await record_event(
                audit_repository,
                actor_user_id=user.id if user is not None else None,
                action="auth.login.failed",
                details={
                    "email": payload.email,
                    "reason": (
                        "account_not_found"
                        if user is None
                        else "account_inactive"
                        if not user.is_active
                        else "invalid_password"
                    ),
                },
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=INVALID_CREDENTIALS,
            )

        # o "segredo" só é enviado pro cliente, o servidor so salva o hash.
        raw_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + session_ttl
        await session_repository.create(
            _hash_session_token(raw_token), user.id, expires_at
        )
        await record_event(
            audit_repository,
            actor_user_id=user.id,
            action="auth.login.succeeded",
            details={"email": user.email, "role": user.role.value},
        )

        # Autenticar de novo no mesmo navegador revoga a sessão anterior.
        if session_token is not None:
            previous_token_hash = _hash_session_token(session_token)
            previous_session = await session_repository.find_by_token_hash(
                previous_token_hash
            )
            if previous_session is not None:
                await record_event(
                    audit_repository,
                    actor_user_id=user.id,
                    action="auth.session.replaced",
                    details={
                        "previous_user_id": previous_session.user_id,
                        "reason": "new_login",
                    },
                )
            await session_repository.delete_by_token_hash(
                previous_token_hash
            )

        # HttpOnly protege contra leitura por javascript, secure exige HTTPS,
        # samesite reduz o envio automatico do cookie em requisições entre sites.
        response.set_cookie(
            key=SESSION_COOKIE,
            value=raw_token,
            max_age=int(session_ttl.total_seconds()),
            path="/",
            secure=cookie_secure,
            httponly=True,
            samesite="lax",
        )
        return {"message": "Login realizado com sucesso"}

    @app.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(
        response: Response,
        session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    ) -> Response:
        """cancela a sessão atual e remove o cookie do navegador."""
        if session_token is not None:
            token_hash = _hash_session_token(session_token)
            stored_session = await session_repository.find_by_token_hash(token_hash)
            await record_event(
                audit_repository,
                actor_user_id=(
                    stored_session.user_id if stored_session is not None else None
                ),
                action="auth.logout",
                details={"had_session": "true"},
            )
            await session_repository.delete_by_token_hash(token_hash)
        else:
            await record_event(
                audit_repository,
                actor_user_id=None,
                action="auth.logout",
                details={"had_session": "false"},
            )
        clear_session_cookie(response)
        response.status_code = status.HTTP_204_NO_CONTENT
        return response

    @app.get("/auth/me")
    async def current_user_info(
        user: User = Depends(get_current_user),
    ) -> dict[str, str]:
        """Exemplo protegido que informa identidade e perfil da sessão atual."""
        return {"id": user.id, "email": user.email, "role": user.role.value}

    return app
