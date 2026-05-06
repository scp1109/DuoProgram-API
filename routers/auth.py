# routers/auth.py
import os
from fastapi import APIRouter, HTTPException, status, Header
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
from database import get_db_connection
from dotenv import load_dotenv
import bcrypt
from jose import JWTError, jwt

load_dotenv()

# -- Configuracion JWT ----------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "2"))

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY no definida en .env. "
        "Generar una con: python -c \"import secrets; print(secrets.token_hex(32))\""
    )

router = APIRouter(prefix="/auth", tags=["auth"])


# -- Modelos --------------------------------------------------
class UserRegister(BaseModel):
    nombre_completo: str
    email: str
    password: str

class UserLogin(BaseModel):
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
    email: str


# -- Helpers --------------------------------------------------
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

def crear_token(user_id: int, email: str) -> str:
    expira = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "exp": expira}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verificar_token(token: str) -> int:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        # sub puede ser None si el token no tiene ese campo
        # (ej. token malformado o generado externamente)
        sub = payload.get("sub")
        if sub is None:
            raise ValueError("Token sin sub")
        return int(sub)
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido o expirado",
        )

def extraer_token(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Formato de token invalido")
    return authorization[len("Bearer "):]


# -- Endpoints ------------------------------------------------
@router.post("/registro", response_model=TokenResponse)
def registro(user: UserRegister):
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    # dictionary=True hace que cada fila llegue como dict en vez de tupla,
    # pero Pylance no lo reconoce como parametro valido (falla del tipado de la libreria)
    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]
    try:
        cursor.execute("SELECT id FROM usuarios WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="El email ya esta registrado")

        password_hash = hash_password(user.password)
        cursor.execute(
            "INSERT INTO usuarios (nombre_completo, email, password_hash) VALUES (%s, %s, %s)",
            (user.nombre_completo, user.email, password_hash),
        )
        connection.commit()

        # lastrowid puede ser None si el INSERT fallo silenciosamente
        if cursor.lastrowid is None:
            raise HTTPException(status_code=500, detail="Error al obtener ID del usuario")
        user_id: int = int(cursor.lastrowid)

        cursor.execute(
            "INSERT INTO historial (usuario_id, accion, detalles) VALUES (%s, %s, %s)",
            (user_id, "registro", f"Usuario {user.email} se registro"),
        )
        connection.commit()

    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()

    return TokenResponse(
        access_token=crear_token(user_id, user.email),
        user=UserResponse(
            id=user_id,
            nombre_completo=user.nombre_completo,
            email=user.email,
            created_at=datetime.now(),
        ),
    )


@router.post("/login", response_model=TokenResponse)
def login(user: UserLogin):
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    # dictionary=True hace que cada fila llegue como dict en vez de tupla,
    # pero Pylance no lo reconoce como parametro valido (falla del tipado de la libreria)
    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]
    try:
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
        connection.commit()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()

    return TokenResponse(
        access_token=crear_token(user_id, email),
        user=UserResponse(
            id=user_id,
            nombre_completo=nombre_completo,
            email=email,
            created_at=created_at,
        ),
    )


@router.get("/perfil")
def get_perfil(authorization: str = Header(...)):
    token = extraer_token(authorization)
    user_id = verificar_token(token)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    # dictionary=True hace que cada fila llegue como dict en vez de tupla,
    # pero Pylance no lo reconoce como parametro valido (falla del tipado de la libreria)
    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]
    try:
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
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()


@router.get("/historial")
def get_historial(authorization: str = Header(...)):
    token = extraer_token(authorization)
    user_id = verificar_token(token)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    # dictionary=True hace que cada fila llegue como dict en vez de tupla,
    # pero Pylance no lo reconoce como parametro valido (falla del tipado de la libreria)
    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]
    try:
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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()


@router.put("/perfil")
def actualizar_perfil(user: UserUpdate, authorization: str = Header(...)):
    token = extraer_token(authorization)
    user_id = verificar_token(token)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    # dictionary=True hace que cada fila llegue como dict en vez de tupla,
    # pero Pylance no lo reconoce como parametro valido (falla del tipado de la libreria)
    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]
    try:
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
        connection.commit()

    except HTTPException:
        raise
    except Exception as e:
        connection.rollback()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()

    return {"message": "Perfil actualizado correctamente"}
