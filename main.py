# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from routers import plan, auth, programas, admin
from database import init_db
import os


class JSONResponseUTF8(JSONResponse):
    """JSONResponse que SI declara el charset.

    Starlette serializa con ensure_ascii=False, asi que el cuerpo lleva
    UTF-8 crudo, pero manda 'application/json' a secas. Cuando el
    Content-Type no declara charset, el estandar HTTP dice que se asuma
    ISO-8859-1, y el paquete http de Dart lo cumple al pie de la letra:
    los nombres de la malla ("Calculo Diferencial", "Constitucion
    Politica") llegaban a la app con las tildes corruptas.

    Declararlo aqui arregla el origen para cualquier cliente. El cliente
    Flutter ademas decodifica UTF-8 explicitamente, asi que queda
    protegido por los dos lados.
    """
    media_type = "application/json; charset=utf-8"


app = FastAPI(
    title="DuoProgram API",
    description="API de planificacion academica para doble programa UTB",
    version="1.0.0",
    default_response_class=JSONResponseUTF8,
)


# default_response_class solo cubre las respuestas de exito: los errores
# los serializa FastAPI con su propio handler, que vuelve a mandar
# 'application/json' sin charset. Se reenvuelven para que TODA respuesta
# de la API declare utf-8, no solo las que salen bien.
def _con_charset(respuesta):
    respuesta.headers["content-type"] = "application/json; charset=utf-8"
    return respuesta


@app.exception_handler(HTTPException)
async def _http_exception_utf8(request: Request, exc: HTTPException):
    return _con_charset(await http_exception_handler(request, exc))


@app.exception_handler(RequestValidationError)
async def _validation_exception_utf8(request: Request, exc: RequestValidationError):
    return _con_charset(await request_validation_exception_handler(request, exc))


# Inicializar base de datos
init_db()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rutas
app.include_router(auth.router)
app.include_router(plan.router)
app.include_router(programas.router)
app.include_router(admin.router)

# Dashboard admin
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "admin")
if os.path.isdir(STATIC_DIR):
    app.mount("/dashboard", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")

# Flutter web app
FLUTTER_DIR = os.path.join(os.path.dirname(__file__), "flutter_web")
if os.path.isdir(FLUTTER_DIR):
    app.mount("/app", StaticFiles(directory=FLUTTER_DIR, html=True), name="flutter_app")

@app.get("/")
def root():
    return {"mensaje": "DuoProgram API funcionando"}

#       uvicorn main:app --reload --host 0.0.0.0 --port 8000
