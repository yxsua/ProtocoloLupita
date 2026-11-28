"""Autenticación mínima para las rutas internas del panel gubernamental."""

from __future__ import annotations

import hmac
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

_basic = HTTPBasic(auto_error=False)


def require_government_user(
    credentials: HTTPBasicCredentials | None = Depends(_basic),
) -> str:
    """No sirve el panel hasta configurar usuario y contraseña."""
    username = os.getenv("GOV_PANEL_USERNAME", "")
    password = os.getenv("GOV_PANEL_PASSWORD", "")
    if not username or not password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="El acceso al panel gubernamental aún no está configurado.",
        )
    if credentials is None or not (
        hmac.compare_digest(credentials.username, username)
        and hmac.compare_digest(credentials.password, password)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales no válidas.",
            headers={"WWW-Authenticate": "Basic realm=\"Panel gubernamental\""},
        )
    return credentials.username
