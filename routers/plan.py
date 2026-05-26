# ============================================================
#  routers/plan.py
#  Los 5 Endpoints de planificación: generar (/planificar), 
#  guardar, listar los del usuario, obtener uno específico y eliminar
# ============================================================

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import json
from motor.planificador import (
    ParametrosPlan, HomologacionExterna, generar_plan
)
from database import get_db_connection
from routers.auth import extraer_token, verificar_token

router = APIRouter(prefix="/plan", tags=["plan"])


# -- Modelos request/response ---------------------------------

class HomologacionRequest(BaseModel):
    codigo_materia: str
    nombre_programa: str


class PlanRequest(BaseModel):
    codigo_programa_principal:  str
    codigo_programa_secundario: Optional[str] = None
    aprobadas:                  List[str] = []
    niveles_ingles_homologados: List[int] = []
    promedio:                   float = 4.0
    semestres_cursados:         int = 0
    homologaciones_externas:    List[HomologacionRequest] = []
    practica_unica:             bool = True
    practica_sola:              bool = False
    # Matricula UTB permite desde 0 cr; el planificador no aplica este campo.
    creditos_minimos:           int = 0


class MateriaPlanResponse(BaseModel):
    codigo:           str
    nombre:           str
    creditos:         int
    origen:           str
    sirve_para_ambas: bool


class SemestrePlanResponse(BaseModel):
    numero:         int
    materias:       List[MateriaPlanResponse]
    total_creditos: int
    es_primero:     bool
    es_ultimo:      bool


class PlanResponse(BaseModel):
    semestres:               List[SemestrePlanResponse]
    total_semestres_futuros: int
    mensaje:                 str


# -- Modelos para guardar planes ------------------------------

class GuardarPlanRequest(BaseModel):
    nombre:              Optional[str] = None
    programa_principal:  str
    programa_secundario: Optional[str] = None
    semestres_cursados:  int
    promedio:            float
    materias_aprobadas:  List[str]
    homologaciones:      List[dict]
    plan_generado:       dict


# -- Endpoint planificar --------------------------------------

@router.post("/planificar", response_model=PlanResponse)
def planificar(
    request: PlanRequest,
    authorization: str = Header(...),
):
    token = extraer_token(authorization)
    verificar_token(token)

    params = ParametrosPlan(
        codigo_programa_principal  = request.codigo_programa_principal,
        codigo_programa_secundario = request.codigo_programa_secundario,
        aprobadas                  = set(request.aprobadas),
        niveles_ingles_homologados = set(request.niveles_ingles_homologados),
        promedio                   = request.promedio,
        semestres_cursados         = request.semestres_cursados,
        homologaciones_externas    = [
            HomologacionExterna(
                codigo_materia  = h.codigo_materia,
                nombre_programa = h.nombre_programa,
            )
            for h in request.homologaciones_externas
        ],
        practica_unica = request.practica_unica,
        practica_sola  = request.practica_sola,
    )

    plan = generar_plan(params)

    semestres_response = [
        SemestrePlanResponse(
            numero         = sem.numero,
            materias       = [
                MateriaPlanResponse(
                    codigo           = m.codigo,
                    nombre           = m.nombre,
                    creditos         = m.creditos,
                    origen           = m.origen,
                    sirve_para_ambas = m.sirve_para_ambas,
                )
                for m in sem.materias
            ],
            total_creditos = sem.total_creditos,
            es_primero     = sem.es_primero,
            es_ultimo      = sem.es_ultimo,
        )
        for sem in plan
    ]

    return PlanResponse(
        semestres               = semestres_response,
        total_semestres_futuros = len(plan),
        mensaje                 = f"Plan generado: {len(plan)} semestres restantes",
    )


# -- Endpoint guardar plan ------------------------------------

@router.post("/guardar-plan")
def guardar_plan(
    request: GuardarPlanRequest,
    authorization: str = Header(...)
):
    token   = extraer_token(authorization)
    user_id = verificar_token(token)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]

    try:
        cursor.execute(
            """
            INSERT INTO planes (
                usuario_id, nombre, programa_principal, programa_secundario,
                semestres_cursados, promedio, materias_aprobadas,
                homologaciones, plan_generado, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                request.nombre,
                request.programa_principal,
                request.programa_secundario,
                request.semestres_cursados,
                request.promedio,
                json.dumps(request.materias_aprobadas),
                json.dumps(request.homologaciones),
                json.dumps(request.plan_generado),
                datetime.now(),
            ),
        )
        connection.commit()

        # lastrowid puede ser None si el INSERT fallo silenciosamente
        if cursor.lastrowid is None:
            raise HTTPException(status_code=500, detail="Error al obtener ID del plan")
        plan_id: int = int(cursor.lastrowid)

        cursor.execute(
            "INSERT INTO historial (usuario_id, accion, detalles) VALUES (%s, %s, %s)",
            (user_id, "generar_plan", f"Plan guardado ID: {plan_id}"),
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

    return {"message": "Plan guardado exitosamente", "plan_id": plan_id}


# -- Endpoint obtener mis planes ------------------------------

@router.get("/mis-planes")
def obtener_mis_planes(authorization: str = Header(...)):
    token   = extraer_token(authorization)
    user_id = verificar_token(token)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]

    try:
        cursor.execute(
            """
            SELECT id, nombre, programa_principal, programa_secundario,
                   semestres_cursados, promedio, plan_generado, created_at
            FROM planes
            WHERE usuario_id = %s
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows: list[dict] = cursor.fetchall()  # type: ignore[assignment]

        planes = []
        for row in rows:
            plan_generado = row["plan_generado"]
            if isinstance(plan_generado, str):
                try:
                    plan_generado = json.loads(plan_generado)
                except Exception:
                    plan_generado = {}

            planes.append({
                "id":                  row["id"],
                "nombre":              row["nombre"],
                "programa_principal":  row["programa_principal"],
                "programa_secundario": row["programa_secundario"],
                "semestres_cursados":  row["semestres_cursados"],
                "promedio":            float(row["promedio"]) if row["promedio"] else 0,
                "plan_generado":       plan_generado,
                "created_at":          row["created_at"].isoformat() if row["created_at"] else None,
            })

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()

    return {"planes": planes}


# -- Endpoint obtener un plan especifico ----------------------

@router.get("/plan/{plan_id}")
def obtener_plan(plan_id: int, authorization: str = Header(...)):
    token   = extraer_token(authorization)
    user_id = verificar_token(token)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]

    try:
        cursor.execute(
            """
            SELECT id, programa_principal, programa_secundario,
                   semestres_cursados, promedio, materias_aprobadas,
                   homologaciones, plan_generado, created_at
            FROM planes
            WHERE id = %s AND usuario_id = %s
            """,
            (plan_id, user_id),
        )
        row: dict = cursor.fetchone()  # type: ignore[assignment]

        if not row:
            raise HTTPException(status_code=404, detail="Plan no encontrado")

        def parse_json(valor: object, default: object) -> object:
            """Parsea JSON si es string; retorna el valor directo si ya es objeto."""
            if isinstance(valor, str):
                try:
                    return json.loads(valor)
                except Exception:
                    return default
            return valor if valor is not None else default

        return {
            "id":                  row["id"],
            "programa_principal":  row["programa_principal"],
            "programa_secundario": row["programa_secundario"],
            "semestres_cursados":  row["semestres_cursados"],
            "promedio":            float(row["promedio"]) if row["promedio"] else 0,
            "created_at":          row["created_at"].isoformat() if row["created_at"] else None,
            "plan_generado":       parse_json(row["plan_generado"], {}),
            "materias_aprobadas":  parse_json(row["materias_aprobadas"], []),
            "homologaciones":      parse_json(row["homologaciones"], []),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()


# -- Endpoint eliminar plan -----------------------------------

@router.delete("/plan/{plan_id}")
def eliminar_plan(plan_id: int, authorization: str = Header(...)):
    token   = extraer_token(authorization)
    user_id = verificar_token(token)

    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    cursor = connection.cursor(dictionary=True)  # type: ignore[call-overload]

    try:
        cursor.execute(
            "DELETE FROM planes WHERE id = %s AND usuario_id = %s",
            (plan_id, user_id),
        )
        connection.commit()

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Plan no encontrado")

        # Registrar en historial que el plan fue eliminado
        cursor.execute(
            "INSERT INTO historial (usuario_id, accion, detalles) VALUES (%s, %s, %s)",
            (user_id, "plan_eliminado", f"Plan ID {plan_id} eliminado"),
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

    return {"message": "Plan eliminado exitosamente"}


# -- Endpoint diagnostico -------------------------------------

@router.post("/diagnostico")
def diagnostico(request: PlanRequest):
    from data.db_programas import PROGRAMAS
    from motor.planificador import (
        cargar_aprobadas, fusionar_grupos,
        calcular_electivas_cubiertas, placeholders_necesarios,
        materias_pendientes, ParametrosPlan, HomologacionExterna,
    )

    prog_p = PROGRAMAS.get(request.codigo_programa_principal)
    prog_s = PROGRAMAS.get(request.codigo_programa_secundario) \
             if request.codigo_programa_secundario else None

    if not prog_p:
        return {"error": f"Programa '{request.codigo_programa_principal}' no encontrado"}

    params = ParametrosPlan(
        codigo_programa_principal  = request.codigo_programa_principal,
        codigo_programa_secundario = request.codigo_programa_secundario,
        aprobadas                  = set(request.aprobadas),
        niveles_ingles_homologados = set(request.niveles_ingles_homologados),
        promedio                   = request.promedio,
        semestres_cursados         = request.semestres_cursados,
        homologaciones_externas    = [
            HomologacionExterna(h.codigo_materia, h.nombre_programa)
            for h in request.homologaciones_externas
        ],
        practica_unica = request.practica_unica,
    )

    aprobadas        = cargar_aprobadas(params, prog_p, prog_s)
    grupos           = fusionar_grupos(prog_p, prog_s)
    cubiertas_grupo  = calcular_electivas_cubiertas(grupos, aprobadas, set(), prog_p, prog_s)
    placeholders     = placeholders_necesarios(grupos, cubiertas_grupo, aprobadas)
    pendientes       = materias_pendientes(prog_p, prog_s, aprobadas, placeholders, params)

    return {
        "total_aprobadas":  len(aprobadas),
        "total_pendientes": len(pendientes),
        "aprobadas":        sorted(aprobadas),
        "pendientes": [
            {"codigo": m.codigo, "nombre": m.nombre, "creditos": m.creditos, "nivel": m.nivel}
            for m in pendientes
        ],
        "grupos_electivas": {
            tc: {
                "nombre":    gf.nombre,
                "cantidad":  gf.cantidad,
                "cubiertas": cubiertas_grupo.get(tc, 0),
                "faltan":    max(0, gf.cantidad - cubiertas_grupo.get(tc, 0)),
                "slots":     gf.slot_codigos,
            }
            for tc, gf in grupos.items()
        },
        "placeholders_necesarios": sorted(placeholders),
    }
