# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import plan, auth, programas
from database import init_db

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

@app.get("/") #flutter pub outdated
def root():
    return {"mensaje": "DuoProgram API funcionando"}

#       uvicorn main:app --reload --host 0.0.0.0 --port 8000
