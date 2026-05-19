# data/db_programas.py
# ============================================================
# Carga los datos de programas, materias, prerrequisitos y
# grupos de electivas desde la base de datos MySQL, y construye
# los mismos objetos (Programa, Materia, GrupoElectiva) que
# antes estaban hardcodeados en programas.py.
#
# El planificador importa de aqui en lugar de programas.py,
# sin necesitar ningun otro cambio en el motor.
# ============================================================

from typing import Dict, List, Optional, Set
from database import get_db_connection
from data.modelos import Materia, GrupoElectiva, Programa


# ----- Funciones de carga desde BD -----------------------------

def _cargar_prerrequisitos(cursor, programa_codigo: str) -> Dict[str, List[str]]:
    """Retorna {materia_codigo: [prereq1, prereq2, ...]} para un programa."""
    cursor.execute(
        "SELECT materia_codigo, prereq_codigo FROM prerrequisitos "
        "WHERE programa_codigo = %s",
        (programa_codigo,),
    )
    prereqs: Dict[str, List[str]] = {}
    for row in cursor.fetchall():
        cod  = row["materia_codigo"]
        pre  = row["prereq_codigo"]
        prereqs.setdefault(cod, []).append(pre)
    return prereqs


def _cargar_materias_programa(cursor, programa_codigo: str) -> List[Materia]:
    """Carga las materias de un programa con sus prerrequisitos."""
    prereqs = _cargar_prerrequisitos(cursor, programa_codigo)

    cursor.execute(
        """
        SELECT m.codigo, m.nombre, m.creditos, pm.nivel,
               m.es_proyecto, m.es_practica, pm.proyecto_compartido
        FROM programa_materia pm
        JOIN materias m ON m.codigo = pm.materia_codigo
        WHERE pm.programa_codigo = %s
        ORDER BY pm.nivel, m.creditos DESC
        """,
        (programa_codigo,),
    )
    materias = []
    for row in cursor.fetchall():
        materias.append(Materia(
            codigo              = row["codigo"],
            nombre              = row["nombre"],
            creditos            = row["creditos"],
            nivel               = row["nivel"],
            prerrequisitos      = prereqs.get(row["codigo"], []),
            es_proyecto         = bool(row["es_proyecto"]),
            es_practica         = bool(row["es_practica"]),
            proyecto_compartido = row["proyecto_compartido"],
        ))
    return materias


def _cargar_grupos_electivas(cursor, programa_codigo: str) -> List[GrupoElectiva]:
    """Carga los grupos de electivas de un programa con sus slots y opciones."""
    # -- Grupos base --
    cursor.execute(
        "SELECT id, tipo_codigo, nombre, cantidad, creditos_cu "
        "FROM grupos_electivas WHERE programa_codigo = %s",
        (programa_codigo,),
    )
    grupos_rows = cursor.fetchall()

    grupos = []
    for gr in grupos_rows:
        grupo_id = gr["id"]

        # -- Slots (placeholders en la malla) --
        cursor.execute(
            "SELECT slot_codigo FROM grupos_electivas_slots WHERE grupo_id = %s",
            (grupo_id,),
        )
        slot_codigos = [r["slot_codigo"] for r in cursor.fetchall()]

        # -- Opciones (materias que pueden cubrir el grupo) --
        cursor.execute(
            """
            SELECT m.codigo, m.nombre, m.creditos
            FROM grupos_electivas_opciones geo
            JOIN materias m ON m.codigo = geo.materia_codigo
            WHERE geo.grupo_id = %s
            """,
            (grupo_id,),
        )
        opciones = [
            Materia(
                codigo         = r["codigo"],
                nombre         = r["nombre"],
                creditos       = r["creditos"],
                nivel          = 0,
                prerrequisitos = [],
            )
            for r in cursor.fetchall()
        ]

        grupos.append(GrupoElectiva(
            tipo_codigo  = gr["tipo_codigo"],
            nombre       = gr["nombre"],
            cantidad     = gr["cantidad"],
            creditos_cu  = gr["creditos_cu"],
            slot_codigos = slot_codigos,
            opciones     = opciones,
        ))

    return grupos


def _cargar_programa(cursor, codigo: str) -> Optional[Programa]:
    """Construye un objeto Programa completo leyendo todas las tablas."""
    cursor.execute(
        "SELECT codigo, nombre, facultad FROM programas WHERE codigo = %s",
        (codigo,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    materias = _cargar_materias_programa(cursor, codigo)
    grupos   = _cargar_grupos_electivas(cursor, codigo)

    return Programa(
        codigo           = row["codigo"],
        nombre           = row["nombre"],
        facultad         = row["facultad"],
        materias         = materias,
        grupos_electivas = grupos,
    )


# ---- Carga global al importar el módulo -----------------------
# Se conecta una sola vez y deja los objetos en memoria,
# igual que antes con programas.py pero directamente desde la BD.

def _cargar_todos() -> Dict[str, Programa]:
    conn = get_db_connection()
    if not conn:
        raise RuntimeError("No se pudo conectar a la BD para cargar programas.")

    # dictionary=True hace que fetchone/fetchall retornen dict en lugar de tupla.
    # Los stubs de mysql-connector no reflejan esto, por eso se usa # type: ignore
    # donde sea necesario para evitar falsos errores de Pylance.
    cursor = conn.cursor(dictionary=True)  # type: ignore[call-overload]
    try:
        cursor.execute("SELECT codigo FROM programas")
        rows: list[dict] = cursor.fetchall()  # type: ignore[assignment]
        codigos = [r["codigo"] for r in rows]
        # Se filtra None explicitamente; la comprension de dict no convence a Pylance
        resultado: Dict[str, Programa] = {}
        for cod in codigos:
            prog = _cargar_programa(cursor, cod)
            if prog is not None:
                resultado[cod] = prog
        return resultado
    finally:
        cursor.close()
        conn.close()


def _cargar_codigos_ingles() -> List[str]:
    conn = get_db_connection()
    if not conn:
        return []
    cursor = conn.cursor(dictionary=True)  # type: ignore[call-overload]
    try:
        cursor.execute(
            "SELECT materia_codigo FROM codigos_ingles ORDER BY nivel_ingles"
        )
        rows: list[dict] = cursor.fetchall()  # type: ignore[assignment]
        return [r["materia_codigo"] for r in rows]
    finally:
        cursor.close()
        conn.close()


# ---- Objetos públicos (misma interfaz que programas.py) ------
PROGRAMAS: Dict[str, Programa] = _cargar_todos()
CODIGOS_INGLES: List[str]      = _cargar_codigos_ingles()


def get_programa(codigo: str) -> Optional[Programa]:
    return PROGRAMAS.get(codigo)


def get_todos_programas() -> List[Programa]:
    return list(PROGRAMAS.values())


def get_codigos_practica() -> Dict[str, str]:
    """Retorna {codigo_programa: codigo_practica} para cada programa."""
    result = {}
    for codigo, prog in PROGRAMAS.items():
        if prog.codigos_practica:
            result[codigo] = list(prog.codigos_practica)[0]
    return result
