# ============================================================
#  routers/admin.py
#  Endpoints del panel de administracion (dashboard).
#  Permite ver estadisticas, usuarios, planes, programas
#  y gestionar la malla curricular desde el dashboard web.
#
#  Estructura de la BD:
#  - programas.codigo (PK string, ej: "ISCO")
#  - materias.codigo  (PK string, ej: "CBAS_C01A")
#  - programa_materia (programa_codigo, materia_codigo, nivel, ...)
#  - prerrequisitos   (programa_codigo, materia_codigo, prereq_codigo)
#  - grupos_electivas (programa_codigo, tipo_codigo, nombre, cantidad, creditos_cu)
# ============================================================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List
from database import get_db_connection
from data.db_programas import recargar_programas

router = APIRouter(prefix="/admin", tags=["admin"])

# Helpers para silenciar los falsos errores de Pylance con mysql-connector.
# cursor(dictionary=True) retorna dicts en runtime, pero los stubs tipan RowType.
def _one(cursor) -> Dict[str, Any]:
    return cursor.fetchone()  # type: ignore[return-value]

def _all(cursor) -> List[Dict[str, Any]]:
    return cursor.fetchall()  # type: ignore[return-value]


# -- Modelos de entrada ---------------------------------------

class ProgramaCreate(BaseModel):
    codigo: str
    nombre: str
    facultad: str
    creditos_totales: int

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
    creditos_totales: int
    materias: List[MateriaCreate]
    grupos_electivas: List[GrupoElectivaCreate] = []


# -- Estadisticas generales -----------------------------------

@router.get("/stats")
def get_stats():
    """Retorna conteos generales para las tarjetas del dashboard."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT COUNT(*) AS total FROM usuarios")
    total_usuarios = _one(cursor)["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM planes")
    total_planes = _one(cursor)["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM programas")
    total_programas = _one(cursor)["total"]

    cursor.execute("SELECT COUNT(*) AS total FROM materias")
    total_materias = _one(cursor)["total"]

    cursor.close()
    conn.close()

    return {
        "total_usuarios": total_usuarios,
        "total_planes": total_planes,
        "total_programas": total_programas,
        "total_materias": total_materias,
    }


# -- Usuarios -------------------------------------------------

@router.get("/usuarios")
def get_usuarios():
    """Lista todos los usuarios registrados."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT id, nombre_completo, email, created_at
        FROM usuarios
        ORDER BY created_at DESC
    """)
    usuarios = _all(cursor)
    cursor.close()
    conn.close()

    for u in usuarios:
        if u.get("created_at"):
            u["created_at"] = str(u["created_at"])

    return {"usuarios": usuarios}


# -- Planes ---------------------------------------------------

@router.get("/planes")
def get_planes():
    """Lista todos los planes generados con el nombre del usuario."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.id, u.nombre_completo AS usuario,
               p.programa_principal, p.programa_secundario,
               p.semestres_cursados, p.promedio, p.created_at
        FROM planes p
        JOIN usuarios u ON p.usuario_id = u.id
        ORDER BY p.created_at DESC
    """)
    planes = _all(cursor)
    cursor.close()
    conn.close()

    for p in planes:
        if p.get("created_at"):
            p["created_at"] = str(p["created_at"])

    return {"planes": planes}


# -- Programas ------------------------------------------------

@router.get("/programas")
def get_programas():
    """Lista todos los programas con sus datos basicos."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT codigo, nombre, facultad, creditos_totales
        FROM programas
        ORDER BY codigo
    """)
    programas = _all(cursor)
    cursor.close()
    conn.close()

    # El dashboard usa "id" para editar/eliminar; la PK real es el codigo.
    for p in programas:
        p["id"] = p["codigo"]

    return {"programas": programas}


@router.get("/programas/{programa_codigo}")
def get_programa_detalle(programa_codigo: str):
    """Retorna un programa con su malla completa (materias y prerrequisitos)."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT codigo, nombre, facultad, creditos_totales
        FROM programas WHERE codigo = %s
    """, (programa_codigo,))
    programa = _one(cursor)
    if not programa:
        cursor.close()
        conn.close()
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
    cursor.close()
    conn.close()

    return programa


@router.post("/programas")
def crear_programa(data: ProgramaCreate):
    """Crea un programa nuevo sin materias."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO programas (codigo, nombre, facultad, creditos_totales)
            VALUES (%s, %s, %s, %s)
        """, (data.codigo.upper(), data.nombre, data.facultad, data.creditos_totales))
        conn.commit()
        recargar_programas()
        return {"id": data.codigo.upper(), "mensaje": "Programa creado correctamente"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.post("/programas/completo")
def crear_programa_completo(data: ProgramaCompleto):
    """Crea un programa con su malla completa en una sola operacion."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor()
    codigo = data.codigo.upper()
    try:
        cursor.execute("""
            INSERT INTO programas (codigo, nombre, facultad, creditos_totales)
            VALUES (%s, %s, %s, %s)
        """, (codigo, data.nombre, data.facultad, data.creditos_totales))

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

        conn.commit()
        recargar_programas()
        return {"id": codigo, "mensaje": "Programa creado correctamente"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.delete("/programas/{programa_codigo}")
def eliminar_programa(programa_codigo: str):
    """Elimina un programa. Las materias compartidas con otros programas se conservan."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM programas WHERE codigo = %s", (programa_codigo,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Programa no encontrado")
        conn.commit()
        recargar_programas()
        return {"mensaje": "Programa eliminado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()


# -- Materias -------------------------------------------------

@router.post("/materias")
def crear_materia(programa_id: str, data: MateriaCreate):
    """Agrega una materia a un programa existente."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor()
    try:
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

        conn.commit()
        recargar_programas()
        return {"id": data.codigo, "mensaje": "Materia creada correctamente"}

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.put("/materias/{materia_codigo}")
def actualizar_materia(materia_codigo: str, data: MateriaUpdate):
    """Actualiza los datos globales de una materia (afecta todos los programas que la usan)."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE materias
            SET nombre = %s, creditos = %s, es_proyecto = %s, es_practica = %s
            WHERE codigo = %s
        """, (data.nombre, data.creditos, data.es_proyecto, data.es_practica, materia_codigo))

        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Materia no encontrada")

        cursor.execute("""
            UPDATE programa_materia SET nivel = %s
            WHERE materia_codigo = %s
        """, (data.nivel, materia_codigo))

        conn.commit()
        recargar_programas()
        return {"mensaje": "Materia actualizada correctamente"}

    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()


@router.delete("/materias/{materia_codigo}")
def eliminar_materia(materia_codigo: str):
    """Elimina una materia y todos sus vinculos con programas y prerrequisitos."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500, detail="Error de conexion a la BD")

    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM materias WHERE codigo = %s", (materia_codigo,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Materia no encontrada")
        conn.commit()
        recargar_programas()
        return {"mensaje": "Materia eliminada correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cursor.close()
        conn.close()
