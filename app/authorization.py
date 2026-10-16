from fastapi import HTTPException, status

from app.auth import Role, User


def require_admin(user: User) -> User:
    """Impede que usuários sem perfil de administrador executem ações administrativas."""
    if user.role is not Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta ação exige perfil de administrador",
        )
    return user
