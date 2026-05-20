# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from routers import plan, auth, programas, admin
from database import init_db
import os

app = FastAPI(
    title="DuoProgram API",
    description="API de planificacion academica para doble programa UTB",
    version="1.0.0",
)

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

# Dashboard admin (archivos estaticos)
# Se sirven en /dashboard para evitar conflicto con el prefix /admin de la API
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "admin")
if os.path.isdir(STATIC_DIR):
    app.mount("/dashboard", StaticFiles(directory=STATIC_DIR, html=True), name="dashboard")

@app.get("/")
def root():
    return {"mensaje": "DuoProgram API funcionando"}

#       uvicorn main:app --reload --host 0.0.0.0 --port 8000
