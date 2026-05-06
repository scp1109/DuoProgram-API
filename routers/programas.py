# routers/programas.py
# Endpoints para consultar programas y mallas desde la base de datos.
# Reemplaza la lectura directa de data/programas.py en memoria.

from fastapi import APIRouter, HTTPException
from database import get_db_connection

router = APIRouter(prefix="/programas", tags=["programas"])


# -- Helpers --------------------------------------------------

def _get_cursor(connection):
    # dictionary=True hace que fetchone/fetchall retornen dict en lugar de tupla.
    # Los stubs de mysql-connector no reflejan esto, por eso se usa # type: ignore
    # donde sea necesario para evitar falsos errores de Pylance.
    return connection.cursor(dictionary=True)


# -- GET /programas -------------------------------------------
# Lista resumida de todos los programas (para la pantalla de seleccion).

@router.get("")
def listar_programas():
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    cursor = _get_cursor(connection)
    try:
        # Creditos totales = obligatorias + electivas (cantidad * creditos_cu)
        cursor.execute("""
            SELECT
                p.codigo,
                p.nombre,
                p.facultad,
                COALESCE(SUM(m.creditos), 0)                        AS creditos_obligatorios,
                COALESCE(
                    (SELECT SUM(ge.cantidad * ge.creditos_cu)
                     FROM grupos_electivas ge
                     WHERE ge.programa_codigo = p.codigo), 0
                )                                                    AS creditos_electivos,
                COUNT(pm.materia_codigo)                             AS total_materias
            FROM programas p
            LEFT JOIN programa_materia pm ON pm.programa_codigo = p.codigo
            LEFT JOIN materias m          ON m.codigo = pm.materia_codigo
            GROUP BY p.codigo, p.nombre, p.facultad
            ORDER BY p.codigo
        """)
        # type: ignore[assignment] porque los stubs tipan fetchall() como lista de tuplas,
        # pero con dictionary=True retorna lista de dict. Se anota manualmente.
        rows: list[dict] = cursor.fetchall()  # type: ignore[assignment]

        return {
            row["codigo"]: {
                "codigo":          row["codigo"],
                "nombre":          row["nombre"],
                "facultad":        row["facultad"],
                "total_creditos":  int(row["creditos_obligatorios"]) + int(row["creditos_electivos"]),
                "total_materias":  int(row["total_materias"]),
            }
            for row in rows
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()


# -- GET /programas/{codigo} ----------------------------------
# Malla completa de un programa: materias, prerrequisitos y grupos de electivas.
# Usada por Flutter para reemplazar datos_programa.dart.

@router.get("/{codigo}")
def get_programa(codigo: str):
    connection = get_db_connection()
    if not connection:
        raise HTTPException(status_code=500, detail="Error de conexion")

    cursor = _get_cursor(connection)
    try:
        # 1. Datos basicos del programa
        cursor.execute(
            "SELECT codigo, nombre, facultad FROM programas WHERE codigo = %s",
            (codigo,),
        )
        # type: ignore[assignment] porque los stubs tipan fetchone() como tupla,
        # pero con dictionary=True retorna dict. Se anota manualmente como dict.
        prog: dict = cursor.fetchone()  # type: ignore[assignment]
        if not prog:
            raise HTTPException(status_code=404, detail=f"Programa '{codigo}' no encontrado")

        # 2. Materias del programa con sus atributos
        cursor.execute("""
            SELECT
                m.codigo,
                m.nombre,
                m.creditos,
                pm.nivel,
                m.es_proyecto,
                m.es_practica,
                pm.proyecto_compartido
            FROM programa_materia pm
            JOIN materias m ON m.codigo = pm.materia_codigo
            WHERE pm.programa_codigo = %s
            ORDER BY pm.nivel, m.codigo
        """, (codigo,))
        filas_materias: list[dict] = cursor.fetchall()  # type: ignore[assignment]

        # 3. Prerrequisitos de todas las materias del programa
        cursor.execute("""
            SELECT materia_codigo, prereq_codigo
            FROM prerrequisitos
            WHERE programa_codigo = %s
        """, (codigo,))
        filas_prereq: list[dict] = cursor.fetchall()  # type: ignore[assignment]

        # Agrupar prerrequisitos por materia para acceso rapido
        prereqs: dict[str, list[str]] = {}
        for fila in filas_prereq:
            cod = str(fila["materia_codigo"])
            prereqs.setdefault(cod, []).append(str(fila["prereq_codigo"]))

        # Construir lista de materias con prerrequisitos incluidos
        materias = [
            {
                "codigo":               str(fila["codigo"]),
                "nombre":               str(fila["nombre"]),
                "creditos":             int(fila["creditos"]),
                "nivel":                int(fila["nivel"]),
                "prerrequisitos":       prereqs.get(str(fila["codigo"]), []),
                "es_proyecto":          bool(fila["es_proyecto"]),
                "es_practica":          bool(fila["es_practica"]),
                "proyecto_compartido":  fila["proyecto_compartido"],
            }
            for fila in filas_materias
        ]

        # 4. Grupos de electivas con sus slots y opciones
        cursor.execute("""
            SELECT id, tipo_codigo, nombre, cantidad, creditos_cu
            FROM grupos_electivas
            WHERE programa_codigo = %s
            ORDER BY id
        """, (codigo,))
        filas_grupos: list[dict] = cursor.fetchall()  # type: ignore[assignment]

        grupos_electivas = []
        for grupo in filas_grupos:
            grupo_id = int(grupo["id"])

            # Slots del grupo
            cursor.execute(
                "SELECT slot_codigo FROM grupos_electivas_slots WHERE grupo_id = %s ORDER BY slot_codigo",
                (grupo_id,),
            )
            slots_rows: list[dict] = cursor.fetchall()  # type: ignore[assignment]
            slots = [str(r["slot_codigo"]) for r in slots_rows]

            # Opciones del grupo (materias que pueden cubrir el slot)
            cursor.execute("""
                SELECT m.codigo, m.nombre, m.creditos
                FROM grupos_electivas_opciones geo
                JOIN materias m ON m.codigo = geo.materia_codigo
                WHERE geo.grupo_id = %s
                ORDER BY m.codigo
            """, (grupo_id,))
            opciones_rows: list[dict] = cursor.fetchall()  # type: ignore[assignment]
            opciones = [
                {
                    "codigo":   str(r["codigo"]),
                    "nombre":   str(r["nombre"]),
                    "creditos": int(r["creditos"]),
                    "nivel":    0,
                }
                for r in opciones_rows
            ]

            grupos_electivas.append({
                "tipo_codigo":  str(grupo["tipo_codigo"]),
                "nombre":       str(grupo["nombre"]),
                "cantidad":     int(grupo["cantidad"]),
                "creditos_cu":  int(grupo["creditos_cu"]),
                "slot_codigos": slots,
                "opciones":     opciones,
            })

        return {
            "codigo":           prog["codigo"],
            "nombre":           prog["nombre"],
            "facultad":         prog["facultad"],
            "materias":         materias,
            "grupos_electivas": grupos_electivas,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")
    finally:
        cursor.close()
        connection.close()
