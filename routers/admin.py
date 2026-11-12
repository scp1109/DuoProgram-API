# ============================================================
#  routers/admin.py
#  Endpoints del panel de administracion (dashboard).
#  Permite ver estadisticas, usuarios, planes, programas
#  y gestionar la malla curricular desde el dashboard web.
#
#  TODOS los endpoints exigen Depends(requiere_admin): un JWT valido
#  cuyo email este en ADMIN_EMAILS. Antes estaban completamente abiertos
#  (cualquiera podia listar usuarios o borrar una malla sin token).
#
#  Estructura de la BD:
#  - programas.codigo (PK string, ej: "ISCO")
#  - materias.codigo  (PK string, ej: "CBAS_C01A")
#  - programa_materia (programa_codigo, materia_codigo, nivel, ...)
#  - prerrequisitos   (programa_codigo, materia_codigo, prereq_codigo)
#  - grupos_electivas (programa_codigo, tipo_codigo, nombre, cantidad, creditos_cu)
# ============================================================

import json

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
from database import get_cursor
from data.db_programas import recargar_programas
from routers.auth import requiere_admin

router = APIRouter(prefix="/admin", tags=["admin"])

# Helpers para silenciar los falsos errores de Pylance con mysql-connector.
# cursor(dictionary=True) retorna dicts en runtime, pero los stubs tipan RowType.
def _one(cursor) -> Dict[str, Any]:
    return cursor.fetchone()  # type: ignore[return-value]

def _all(cursor) -> List[Dict[str, Any]]:
    return cursor.fetchall()  # type: ignore[return-value]


def _error_generico(operacion: str, e: Exception, status_code: int = 400) -> HTTPException:
    """Registra el error real en el servidor y devuelve uno generico al cliente.

    Antes se enviaba detail=str(e), que filtraba el mensaje crudo de MySQL
    (nombres de tablas, columnas y SQL) a cualquiera que llamara el endpoint.
    """
    print(f"[admin] Error en {operacion}: {e}")
    return HTTPException(
        status_code=status_code,
        detail=f"No se pudo completar la operacion ({operacion}). Revise los datos e intente de nuevo.",
    )


# -- Modelos de entrada ---------------------------------------

class ProgramaCreate(BaseModel):
    codigo: str
    nombre: str
    facultad: str

class MateriaCreate(BaseModel):
    codigo: str
    nombre: str
    creditos: int
    nivel: int
    es_proyecto: bool = False
    es_practica: bool = False
    prerrequisitos: List[str] = []

class MateriaUpdate(BaseModel):
    codigo: str
    nombre: str
    creditos: int
    nivel: int
    es_proyecto: bool = False
    es_practica: bool = False
    prerrequisitos: List[str] = []

class GrupoElectivaCreate(BaseModel):
    tipo_codigo: str
    nombre: str
    cantidad: int
    creditos_cu: int
    slot_codigos: List[str]
    opciones: List[str] = []

class ProgramaCompleto(BaseModel):
    codigo: str
    nombre: str
    facultad: str
    materias: List[MateriaCreate]
    grupos_electivas: List[GrupoElectivaCreate] = []


# -- Estadisticas generales -----------------------------------

@router.get("/stats")
def get_stats(_admin: int = Depends(requiere_admin)):
    """Retorna conteos generales para las tarjetas del dashboard."""
    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM usuarios")
        total_usuarios = _one(cursor)["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM planes")
        total_planes = _one(cursor)["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM programas")
        total_programas = _one(cursor)["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM materias")
        total_materias = _one(cursor)["total"]

    return {
        "total_usuarios": total_usuarios,
        "total_planes": total_planes,
        "total_programas": total_programas,
        "total_materias": total_materias,
    }


# -- Usuarios -------------------------------------------------

@router.get("/usuarios")
def get_usuarios(_admin: int = Depends(requiere_admin)):
    """Lista todos los usuarios registrados."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT id, nombre_completo, email, created_at
            FROM usuarios
            ORDER BY created_at DESC
        """)
        usuarios = _all(cursor)

    for u in usuarios:
        if u.get("created_at"):
            u["created_at"] = str(u["created_at"])

    return {"usuarios": usuarios}


# -- Planes ---------------------------------------------------

@router.get("/planes")
def get_planes(_admin: int = Depends(requiere_admin)):
    """Lista todos los planes generados con el nombre del usuario."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT p.id, u.nombre_completo AS usuario,
                   p.programa_principal, p.programa_secundario,
                   p.semestres_cursados, p.promedio, p.created_at
            FROM planes p
            JOIN usuarios u ON p.usuario_id = u.id
            ORDER BY p.created_at DESC
        """)
        planes = _all(cursor)

    for p in planes:
        if p.get("created_at"):
            p["created_at"] = str(p["created_at"])

    return {"planes": planes}


@router.get("/planes/{plan_id}")
def get_plan_detalle(plan_id: int, _admin: int = Depends(requiere_admin)):
    """Retorna el detalle completo de un plan incluyendo el JSON generado."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT p.id, u.nombre_completo AS usuario,
                   p.programa_principal, p.programa_secundario,
                   pp.nombre AS nombre_principal,
                   ps.nombre AS nombre_secundario,
                   p.semestres_cursados, p.promedio, p.plan_generado, p.created_at
            FROM planes p
            JOIN usuarios u ON p.usuario_id = u.id
            LEFT JOIN programas pp ON p.programa_principal = pp.codigo
            LEFT JOIN programas ps ON p.programa_secundario = ps.codigo
            WHERE p.id = %s
        """, (plan_id,))
        plan = _one(cursor)

    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")

    if plan.get("created_at"):
        plan["created_at"] = str(plan["created_at"])

    # plan_generado viene como string JSON desde la BD
    if isinstance(plan.get("plan_generado"), str):
        plan["plan_generado"] = json.loads(plan["plan_generado"])

    return plan


@router.get("/programas")
def get_programas(_admin: int = Depends(requiere_admin)):
    """Lista todos los programas con sus datos basicos."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT p.codigo, p.nombre, p.facultad,
                   COALESCE(MAX(pm.nivel), 0) AS total_semestres
            FROM programas p
            LEFT JOIN programa_materia pm ON p.codigo = pm.programa_codigo
            GROUP BY p.codigo, p.nombre, p.facultad
            ORDER BY p.codigo
        """)
        programas = _all(cursor)

    # El dashboard usa "id" para editar/eliminar; la PK real es el codigo.
    for p in programas:
        p["id"] = p["codigo"]

    return {"programas": programas}


@router.get("/programas/{programa_codigo}")
def get_programa_detalle(programa_codigo: str, _admin: int = Depends(requiere_admin)):
    """Retorna un programa con su malla completa (materias y prerrequisitos)."""
    with get_cursor() as cursor:
        cursor.execute("""
            SELECT codigo, nombre, facultad
            FROM programas WHERE codigo = %s
        """, (programa_codigo,))
        programa = _one(cursor)
        if not programa:
            # get_cursor cierra cursor y conexion al salir del with, incluso
            # cuando se sale por una excepcion.
            raise HTTPException(status_code=404, detail="Programa no encontrado")

        cursor.execute("""
            SELECT m.codigo, m.nombre, m.creditos, pm.nivel,
                   m.es_proyecto, m.es_practica
            FROM materias m
            JOIN programa_materia pm ON m.codigo = pm.materia_codigo
            WHERE pm.programa_codigo = %s
            ORDER BY pm.nivel, m.nombre
        """, (programa_codigo,))
        materias = _all(cursor)

        for mat in materias:
            cursor.execute("""
                SELECT prereq_codigo FROM prerrequisitos
                WHERE programa_codigo = %s AND materia_codigo = %s
            """, (programa_codigo, mat["codigo"]))
            mat["prerrequisitos"] = [r["prereq_codigo"] for r in _all(cursor)]
            mat["es_proyecto"] = bool(mat["es_proyecto"])
            mat["es_practica"] = bool(mat["es_practica"])
            mat["id"] = mat["codigo"]

    programa["materias"] = materias
    programa["id"] = programa["codigo"]

    return programa


@router.post("/programas")
def crear_programa(data: ProgramaCreate, _admin: int = Depends(requiere_admin)):
    """Crea un programa nuevo sin materias."""
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO programas (codigo, nombre, facultad)
                VALUES (%s, %s, %s)
            """, (data.codigo.upper(), data.nombre, data.facultad))
    except HTTPException:
        raise
    except Exception as e:
        raise _error_generico("crear_programa", e)

    # Recargar la cache en memoria solo despues del commit, que ahora
    # ocurre al salir del with.
    recargar_programas()
    return {"id": data.codigo.upper(), "mensaje": "Programa creado correctamente"}


@router.post("/programas/completo")
def crear_programa_completo(data: ProgramaCompleto, _admin: int = Depends(requiere_admin)):
    """Crea un programa con su malla completa en una sola operacion."""
    codigo = data.codigo.upper()
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO programas (codigo, nombre, facultad)
                VALUES (%s, %s, %s)
            """, (codigo, data.nombre, data.facultad))

            for mat in data.materias:
                cursor.execute("""
                    INSERT INTO materias (codigo, nombre, creditos, es_proyecto, es_practica)
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE nombre = VALUES(nombre)
                """, (mat.codigo, mat.nombre, mat.creditos, mat.es_proyecto, mat.es_practica))

                cursor.execute("""
                    INSERT IGNORE INTO programa_materia (programa_codigo, materia_codigo, nivel)
                    VALUES (%s, %s, %s)
                """, (codigo, mat.codigo, mat.nivel))

                for pre_codigo in mat.prerrequisitos:
                    cursor.execute("""
                        INSERT IGNORE INTO prerrequisitos (programa_codigo, materia_codigo, prereq_codigo)
                        VALUES (%s, %s, %s)
                    """, (codigo, mat.codigo, pre_codigo))

            for grupo in data.grupos_electivas:
                cursor.execute("""
                    INSERT INTO grupos_electivas (programa_codigo, tipo_codigo, nombre, cantidad, creditos_cu)
                    VALUES (%s, %s, %s, %s, %s)
                """, (codigo, grupo.tipo_codigo, grupo.nombre, grupo.cantidad, grupo.creditos_cu))
                grupo_id = cursor.lastrowid

                for slot_codigo in grupo.slot_codigos:
                    cursor.execute("""
                        INSERT INTO grupos_electivas_slots (grupo_id, slot_codigo)
                        VALUES (%s, %s)
                    """, (grupo_id, slot_codigo))

                for opcion_codigo in grupo.opciones:
                    cursor.execute("""
                        INSERT INTO grupos_electivas_opciones (grupo_id, materia_codigo)
                        VALUES (%s, %s)
                    """, (grupo_id, opcion_codigo))
    except HTTPException:
        raise
    except Exception as e:
        raise _error_generico("crear_programa_completo", e)

    recargar_programas()
    return {"id": codigo, "mensaje": "Programa creado correctamente"}


@router.delete("/programas/{programa_codigo}")
def eliminar_programa(programa_codigo: str, _admin: int = Depends(requiere_admin)):
    """Elimina un programa. Las materias compartidas con otros programas se conservan."""
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("DELETE FROM programas WHERE codigo = %s", (programa_codigo,))
            if cursor.rowcount == 0:
                # Sale del with por excepcion: get_cursor hace rollback y cierra.
                raise HTTPException(status_code=404, detail="Programa no encontrado")
    except HTTPException:
        raise
    except Exception as e:
        raise _error_generico("eliminar_programa", e)

    recargar_programas()
    return {"mensaje": "Programa eliminado correctamente"}


# -- Materias -------------------------------------------------

@router.post("/materias")
def crear_materia(
    programa_id: str,
    data: MateriaCreate,
    _admin: int = Depends(requiere_admin),
):
    """Agrega una materia a un programa existente."""
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("""
                INSERT INTO materias (codigo, nombre, creditos, es_proyecto, es_practica)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    nombre = VALUES(nombre),
                    creditos = VALUES(creditos)
            """, (data.codigo, data.nombre, data.creditos, data.es_proyecto, data.es_practica))

            cursor.execute("""
                INSERT IGNORE INTO programa_materia (programa_codigo, materia_codigo, nivel)
                VALUES (%s, %s, %s)
            """, (programa_id, data.codigo, data.nivel))

            cursor.execute("""
                DELETE FROM prerrequisitos
                WHERE programa_codigo = %s AND materia_codigo = %s
            """, (programa_id, data.codigo))

            for pre_codigo in data.prerrequisitos:
                cursor.execute("""
                    INSERT IGNORE INTO prerrequisitos (programa_codigo, materia_codigo, prereq_codigo)
                    VALUES (%s, %s, %s)
                """, (programa_id, data.codigo, pre_codigo))
    except HTTPException:
        raise
    except Exception as e:
        raise _error_generico("crear_materia", e)

    recargar_programas()
    return {"id": data.codigo, "mensaje": "Materia creada correctamente"}


@router.put("/programas/{programa_codigo}/materias/{materia_codigo}")
def actualizar_materia_programa(
    programa_codigo: str,
    materia_codigo: str,
    data: MateriaUpdate,
    _admin: int = Depends(requiere_admin),
):
    """Actualiza una materia dentro de un programa.

    nombre/creditos/tipo son datos globales de la materia.
    nivel y prerrequisitos se actualizan solo para el programa indicado.
    """
    programa_codigo = programa_codigo.upper()

    if data.codigo != materia_codigo:
        raise HTTPException(
            status_code=400,
            detail="No se puede cambiar el codigo de una materia existente desde este formulario",
        )

    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("SELECT 1 FROM materias WHERE codigo = %s", (materia_codigo,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Materia no encontrada")

            cursor.execute("""
                SELECT 1 FROM programa_materia
                WHERE programa_codigo = %s AND materia_codigo = %s
            """, (programa_codigo, materia_codigo))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="La materia no esta vinculada a este programa",
                )

            cursor.execute("""
                UPDATE materias
                SET nombre = %s, creditos = %s, es_proyecto = %s, es_practica = %s
                WHERE codigo = %s
            """, (data.nombre, data.creditos, data.es_proyecto, data.es_practica, materia_codigo))

            cursor.execute("""
                UPDATE programa_materia SET nivel = %s
                WHERE programa_codigo = %s AND materia_codigo = %s
            """, (data.nivel, programa_codigo, materia_codigo))

            cursor.execute("""
                DELETE FROM prerrequisitos
                WHERE programa_codigo = %s AND materia_codigo = %s
            """, (programa_codigo, materia_codigo))

            for pre_codigo in data.prerrequisitos:
                cursor.execute("""
                    INSERT IGNORE INTO prerrequisitos (programa_codigo, materia_codigo, prereq_codigo)
                    VALUES (%s, %s, %s)
                """, (programa_codigo, materia_codigo, pre_codigo))
    except HTTPException:
        raise
    except Exception as e:
        raise _error_generico("actualizar_materia_programa", e)

    recargar_programas()
    return {"mensaje": "Materia actualizada correctamente"}


@router.delete("/programas/{programa_codigo}/materias/{materia_codigo}")
def eliminar_materia_de_programa(
    programa_codigo: str,
    materia_codigo: str,
    _admin: int = Depends(requiere_admin),
):
    """Quita una materia solo del programa indicado.

    La materia global se conserva porque puede estar compartida con otros programas.
    """
    programa_codigo = programa_codigo.upper()
    try:
        with get_cursor(commit=True) as cursor:
            cursor.execute("""
                SELECT 1 FROM programa_materia
                WHERE programa_codigo = %s AND materia_codigo = %s
            """, (programa_codigo, materia_codigo))
            if not cursor.fetchone():
                raise HTTPException(
                    status_code=404,
                    detail="La materia no esta vinculada a este programa",
                )

            cursor.execute("""
                DELETE FROM prerrequisitos
                WHERE programa_codigo = %s
                  AND (materia_codigo = %s OR prereq_codigo = %s)
            """, (programa_codigo, materia_codigo, materia_codigo))

            cursor.execute("""
                DELETE FROM programa_materia
                WHERE programa_codigo = %s AND materia_codigo = %s
            """, (programa_codigo, materia_codigo))
    except HTTPException:
        raise
    except Exception as e:
        raise _error_generico("eliminar_materia_de_programa", e)

    recargar_programas()
    return {"mensaje": "Materia quitada del programa correctamente"}
