# routers/auth.py
import os
from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel, EmailStr
from typing import Any, Dict, Optional
from datetime import datetime, timedelta, timezone
from database import get_cursor
from dotenv import load_dotenv
import bcrypt
from jose import JWTError, jwt

load_dotenv()

# -- Configuracion JWT ----------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

# Largo minimo de contrasena. Estaba escrito solo en /cambiar-password y el
# registro no validaba nada, asi que se podia crear una cuenta con 1 caracter
# y despues no poder cambiarla por una igual de corta. Se centraliza aqui.
PASSWORD_MIN_LEN = 8

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY no definida en .env. "
        "Generar una con: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

# -- Administradores ------------------------------------------
# No hay columna es_admin en la BD (se decidio no migrar), asi que la lista de
# admins vive en la variable de entorno ADMIN_EMAILS, separada por comas.
# Se normaliza a minusculas para comparar sin importar como se escribio el email.
def _cargar_admin_emails() -> frozenset:
    crudo = os.getenv("ADMIN_EMAILS", "")
    return frozenset(
        e.strip().lower() for e in crudo.split(",") if e.strip()
    )

ADMIN_EMAILS = _cargar_admin_emails()

router = APIRouter(prefix="/auth", tags=["auth"])


# -- Modelos --------------------------------------------------
class UserRegister(BaseModel):
    nombre_completo: str
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    # A proposito NO es EmailStr: en la BD ya hay cuentas creadas cuando el
    # registro aceptaba cualquier string, y algunas tienen emails que
    # email-validator rechaza. Validar aqui dejaria a esos usuarios sin poder
    # entrar. El registro si valida, asi que las cuentas nuevas son correctas.
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    nombre_completo: str
    email: str
    created_at: Optional[datetime] = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class UserUpdate(BaseModel):
    nombre_completo: str
    email: EmailStr


class CambiarPasswordRequest(BaseModel):
    old_password: str
    new_password: str


# -- Helpers --------------------------------------------------
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def crear_token(user_id: int, email: str) -> str:
    # datetime.utcnow() quedo deprecado en Python 3.12 porque devuelve un
    # datetime naive; now(timezone.utc) es explicito y da el mismo instante.
    expira = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "exp": expira}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decodificar_token(token: str) -> Dict[str, Any]:
    """Verifica la firma/expiracion y devuelve el payload completo.

    verificar_token solo entrega el user_id, pero la comprobacion de admin
    necesita el email del claim. Se separa aqui para no duplicar la logica
    de decodificacion en dos sitios.
    """
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        )

def verificar_token(token: str) -> int:
    # La firma se mantiene (token -> user_id) porque routers/plan.py la usa asi.
    payload = decodificar_token(token)
    try:
        # sub puede ser None si el token no tiene ese campo
        # (ej. token malformado o generado externamente)
        sub = payload.get("sub")
        if sub is None:
            raise ValueError("Token sin sub")
        return int(sub)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        )

def extraer_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Formato de token invalido")
    return authorization[len("Bearer "):]


def requiere_admin(authorization: str = Header(default="")) -> int:
    """Dependencia para los endpoints /admin/*: exige un JWT valido cuyo
    email este en ADMIN_EMAILS. Devuelve el user_id del admin.

    Fail-closed: si ADMIN_EMAILS no esta configurada se rechaza todo antes
    incluso de mirar el token. Nunca se debe abrir el panel por defecto solo
    porque falte una variable de entorno.

    El header se declara con default="" (y no Header(...)) para que una peticion
    sin Authorization responda 401 y no el 422 de validacion de FastAPI: falta
    de credenciales no es un error de formato del request.
    """
    if not ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Acceso administrativo deshabilitado: falta configurar la "
                "variable de entorno ADMIN_EMAILS (emails separados por coma)."
            ),
        )

    token = extraer_token(authorization)
    payload = decodificar_token(token)

    email = str(payload.get("email") or "").strip().lower()
    if not email or email not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tiene permisos de administrador",
        )

    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        )
    return int(sub)


# -- Endpoints ------------------------------------------------
@router.post("/registro", response_model=TokenResponse)
def registro(user: UserRegister):
    if len(user.password) < PASSWORD_MIN_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"La contrasena debe tener al menos {PASSWORD_MIN_LEN} caracteres",
        )

    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("SELECT id FROM usuarios WHERE email = %s", (user.email,))
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="El email ya esta registrado")

            password_hash = hash_password(user.password)
            cursor.execute(
                "INSERT INTO usuarios (nombre_completo, email, password_hash) VALUES (%s, %s, %s)",
                (user.nombre_completo, user.email, password_hash),
            )

            # lastrowid puede ser None si el INSERT fallo silenciosamente
            if cursor.lastrowid is None:
                raise HTTPException(status_code=500, detail="Error al obtener ID del usuario")
            user_id: int = int(cursor.lastrowid)

            # Sin commit intermedio: usuario e historial entran en la misma
            # transaccion, asi no queda un usuario sin su registro de historial.
            cursor.execute(
                "INSERT INTO historial (usuario_id, accion, detalles) VALUES (%s, %s, %s)",
                (user_id, "registro", f"Usuario {user.email} se registro"),
            )

        return TokenResponse(
            access_token=crear_token(user_id, user.email),
            user=UserResponse(
                id=user_id,
                nombre_completo=user.nombre_completo,
                email=user.email,
                created_at=datetime.now(),
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        # El error real (nombres de tablas, SQL) se queda en el log del
        # servidor; al cliente solo le llega un mensaje generico.
        print(f"[auth] Error en registro: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/login", response_model=TokenResponse)
def login(user: UserLogin):
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "SELECT id, nombre_completo, email, password_hash, created_at "
                "FROM usuarios WHERE email = %s",
                (user.email,),
            )
            row: dict = cursor.fetchone()  # type: ignore[assignment]

            if row is None:
                raise HTTPException(status_code=401, detail="Email o contrasena incorrectos")

            user_id: int                   = int(row["id"])
            nombre_completo: str           = str(row["nombre_completo"])
            email: str                     = str(row["email"])
            password_hash: str             = str(row["password_hash"])
            created_at: Optional[datetime] = row["created_at"]

            if not verify_password(user.password, password_hash):
                raise HTTPException(status_code=401, detail="Email o contrasena incorrectos")

            cursor.execute(
                "INSERT INTO historial (usuario_id, accion, detalles) VALUES (%s, %s, %s)",
                (user_id, "login", f"Inicio de sesion de {email}"),
            )

        return TokenResponse(
            access_token=crear_token(user_id, email),
            user=UserResponse(
                id=user_id,
                nombre_completo=nombre_completo,
                email=email,
                created_at=created_at,
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"[auth] Error en login: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/perfil")
def get_perfil(authorization: str = Header(...)):
    token = extraer_token(authorization)
    user_id = verificar_token(token)

    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT id, nombre_completo, email, created_at FROM usuarios WHERE id = %s",
                (user_id,),
            )
            row: dict = cursor.fetchone()  # type: ignore[assignment]

        if row is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        return {
            "id":              row["id"],
            "nombre_completo": row["nombre_completo"],
            "email":           row["email"],
            "created_at":      row["created_at"],
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"[auth] Error en get_perfil: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.get("/historial")
def get_historial(authorization: str = Header(...)):
    token = extraer_token(authorization)
    user_id = verificar_token(token)

    try:
        with get_cursor() as cursor:
            cursor.execute(
                "SELECT id, accion, detalles, fecha FROM historial "
                "WHERE usuario_id = %s ORDER BY fecha DESC LIMIT 50",
                (user_id,),
            )
            rows: list[dict] = cursor.fetchall()  # type: ignore[assignment]

        return [
            {"id": r["id"], "accion": r["accion"], "detalles": r["detalles"], "fecha": r["fecha"]}
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        print(f"[auth] Error en get_historial: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.put("/perfil")
def actualizar_perfil(user: UserUpdate, authorization: str = Header(...)):
    token = extraer_token(authorization)
    user_id = verificar_token(token)

    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "SELECT id FROM usuarios WHERE email = %s AND id != %s",
                (user.email, user_id),
            )
            if cursor.fetchone():
                raise HTTPException(status_code=400, detail="El email ya esta en uso")

            cursor.execute(
                "UPDATE usuarios SET nombre_completo = %s, email = %s WHERE id = %s",
                (user.nombre_completo, user.email, user_id),
            )

            # Registrar en historial que el perfil fue actualizado
            cursor.execute(
                "INSERT INTO historial (usuario_id, accion, detalles) VALUES (%s, %s, %s)",
                (user_id, "actualizar_perfil", f"Nombre: {user.nombre_completo} | Email: {user.email}"),
            )

        return {"message": "Perfil actualizado correctamente"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[auth] Error en actualizar_perfil: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")


@router.post("/cambiar-password")
def cambiar_password(
    body: CambiarPasswordRequest,
    authorization: str = Header(...),
):
    token = extraer_token(authorization)
    user_id = verificar_token(token)

    if len(body.new_password) < PASSWORD_MIN_LEN:
        raise HTTPException(
            status_code=400,
            detail=f"La nueva contrasena debe tener al menos {PASSWORD_MIN_LEN} caracteres",
        )

    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute(
                "SELECT password_hash FROM usuarios WHERE id = %s",
                (user_id,),
            )
            row: dict = cursor.fetchone()  # type: ignore[assignment]
            if row is None:
                raise HTTPException(status_code=404, detail="Usuario no encontrado")

            if not verify_password(body.old_password, str(row["password_hash"])):
                raise HTTPException(
                    status_code=400,
                    detail="La contrasena actual es incorrecta",
                )

            nuevo_hash = hash_password(body.new_password)
            cursor.execute(
                "UPDATE usuarios SET password_hash = %s WHERE id = %s",
                (nuevo_hash, user_id),
            )

            cursor.execute(
                "INSERT INTO historial (usuario_id, accion, detalles) VALUES (%s, %s, %s)",
                (user_id, "password_cambiado", "Contrasena actualizada"),
            )

        return {"message": "Contrasena actualizada correctamente"}

    except HTTPException:
        raise
    except Exception as e:
        print(f"[auth] Error en cambiar_password: {e}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")
