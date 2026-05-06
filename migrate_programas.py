"""
migrate_programas.py
--------------------
Migra toda la data de PROGRAMAS_DATA (programas.py) a la base
de datos duoprogram_db en MySQL.

Uso:
    python migrate_programas.py

Requiere que duoprogram_db ya exista y que .env tenga las credenciales.
"""

import os
import pymysql
from dotenv import load_dotenv
from data.programas import PROGRAMAS_DATA, CODIGOS_INGLES

load_dotenv()

# -- Conexion -------------------------------------------------
def get_conn():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "duoprogram_db"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


# -- DDL: crear tablas ----------------------------------------
DDL_STATEMENTS = [
    """CREATE TABLE IF NOT EXISTS programas (
        codigo      VARCHAR(10)  PRIMARY KEY,
        nombre      VARCHAR(120) NOT NULL,
        facultad    VARCHAR(100) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS materias (
        codigo              VARCHAR(20)  PRIMARY KEY,
        nombre              VARCHAR(120) NOT NULL,
        creditos            INT          NOT NULL DEFAULT 0,
        es_proyecto         TINYINT(1)   NOT NULL DEFAULT 0,
        es_practica         TINYINT(1)   NOT NULL DEFAULT 0
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS programa_materia (
        programa_codigo     VARCHAR(10) NOT NULL,
        materia_codigo      VARCHAR(20) NOT NULL,
        nivel               INT         NOT NULL DEFAULT 0,
        proyecto_compartido VARCHAR(20) DEFAULT NULL,
        PRIMARY KEY (programa_codigo, materia_codigo),
        FOREIGN KEY (programa_codigo) REFERENCES programas(codigo),
        FOREIGN KEY (materia_codigo)  REFERENCES materias(codigo)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS prerrequisitos (
        programa_codigo     VARCHAR(10) NOT NULL,
        materia_codigo      VARCHAR(20) NOT NULL,
        prereq_codigo       VARCHAR(20) NOT NULL,
        PRIMARY KEY (programa_codigo, materia_codigo, prereq_codigo),
        FOREIGN KEY (programa_codigo) REFERENCES programas(codigo),
        FOREIGN KEY (materia_codigo)  REFERENCES materias(codigo),
        FOREIGN KEY (prereq_codigo)   REFERENCES materias(codigo)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS grupos_electivas (
        id              INT AUTO_INCREMENT PRIMARY KEY,
        programa_codigo VARCHAR(10)  NOT NULL,
        tipo_codigo     VARCHAR(30)  NOT NULL,
        nombre          VARCHAR(100) NOT NULL,
        cantidad        INT          NOT NULL DEFAULT 1,
        creditos_cu     INT          NOT NULL DEFAULT 0,
        FOREIGN KEY (programa_codigo) REFERENCES programas(codigo)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS grupos_electivas_slots (
        grupo_id        INT         NOT NULL,
        slot_codigo     VARCHAR(20) NOT NULL,
        PRIMARY KEY (grupo_id, slot_codigo),
        FOREIGN KEY (grupo_id) REFERENCES grupos_electivas(id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS grupos_electivas_opciones (
        grupo_id        INT         NOT NULL,
        materia_codigo  VARCHAR(20) NOT NULL,
        PRIMARY KEY (grupo_id, materia_codigo),
        FOREIGN KEY (grupo_id)        REFERENCES grupos_electivas(id),
        FOREIGN KEY (materia_codigo)  REFERENCES materias(codigo)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",

    """CREATE TABLE IF NOT EXISTS codigos_ingles (
        materia_codigo  VARCHAR(20) PRIMARY KEY,
        nivel_ingles    INT         NOT NULL,
        FOREIGN KEY (materia_codigo) REFERENCES materias(codigo)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""",
]


def crear_tablas(cursor):
    print("Creando tablas...")
    for stmt in DDL_STATEMENTS:
        cursor.execute(stmt)
    print("  OK")


# -- Recopilar todas las materias unicas ----------------------
def recopilar_materias(programas_data):
    catalogo = {}
    for prog_data in programas_data.values():
        for m in prog_data["materias"]:
            if m["codigo"] not in catalogo:
                catalogo[m["codigo"]] = {
                    "nombre":      m["nombre"],
                    "creditos":    m["creditos"],
                    "es_proyecto": int(m.get("es_proyecto", False)),
                    "es_practica": int(m.get("es_practica", False)),
                }
        for ge in prog_data.get("grupos_electivas", []):
            for opt in ge.get("opciones", []):
                if opt["codigo"] not in catalogo:
                    catalogo[opt["codigo"]] = {
                        "nombre":      opt["nombre"],
                        "creditos":    opt["creditos"],
                        "es_proyecto": 0,
                        "es_practica": 0,
                    }
    return catalogo


# -- Inserts --------------------------------------------------
def insertar_programas(cursor, programas_data):
    print("Insertando programas...")
    for codigo, data in programas_data.items():
        cursor.execute(
            "INSERT IGNORE INTO programas (codigo, nombre, facultad) VALUES (%s, %s, %s)",
            (codigo, data["nombre"], data["facultad"]),
        )
    print(f"  {len(programas_data)} programas OK")


def insertar_materias(cursor, catalogo):
    print(f"Insertando {len(catalogo)} materias en catalogo...")
    for codigo, info in catalogo.items():
        cursor.execute(
            "INSERT IGNORE INTO materias (codigo, nombre, creditos, es_proyecto, es_practica) "
            "VALUES (%s, %s, %s, %s, %s)",
            (codigo, info["nombre"], info["creditos"], info["es_proyecto"], info["es_practica"]),
        )
    print("  OK")


def insertar_programa_materia(cursor, programas_data):
    print("Insertando programa_materia y prerrequisitos...")
    total_pm = 0
    total_pr = 0
    for prog_codigo, data in programas_data.items():
        for m in data["materias"]:
            cursor.execute(
                "INSERT IGNORE INTO programa_materia "
                "(programa_codigo, materia_codigo, nivel, proyecto_compartido) "
                "VALUES (%s, %s, %s, %s)",
                (prog_codigo, m["codigo"], m["nivel"], m.get("proyecto_compartido")),
            )
            total_pm += 1
            for prereq in m.get("prerrequisitos", []):
                cursor.execute(
                    "INSERT IGNORE INTO prerrequisitos "
                    "(programa_codigo, materia_codigo, prereq_codigo) VALUES (%s, %s, %s)",
                    (prog_codigo, m["codigo"], prereq),
                )
                total_pr += 1
    print(f"  {total_pm} filas programa_materia, {total_pr} prerrequisitos OK")


def insertar_grupos_electivas(cursor, programas_data):
    print("Insertando grupos de electivas...")
    total_grupos = 0
    total_slots = 0
    total_opciones = 0
    for prog_codigo, data in programas_data.items():
        for ge in data.get("grupos_electivas", []):
            cursor.execute(
                "INSERT INTO grupos_electivas "
                "(programa_codigo, tipo_codigo, nombre, cantidad, creditos_cu) "
                "VALUES (%s, %s, %s, %s, %s)",
                (prog_codigo, ge["tipo_codigo"], ge["nombre"], ge["cantidad"], ge["creditos_cu"]),
            )
            grupo_id = cursor.lastrowid
            total_grupos += 1
            for slot in ge.get("slot_codigos", []):
                cursor.execute(
                    "INSERT IGNORE INTO grupos_electivas_slots (grupo_id, slot_codigo) VALUES (%s, %s)",
                    (grupo_id, slot),
                )
                total_slots += 1
            for opt in ge.get("opciones", []):
                cursor.execute(
                    "INSERT IGNORE INTO grupos_electivas_opciones (grupo_id, materia_codigo) VALUES (%s, %s)",
                    (grupo_id, opt["codigo"]),
                )
                total_opciones += 1
    print(f"  {total_grupos} grupos, {total_slots} slots, {total_opciones} opciones OK")


def insertar_codigos_ingles(cursor, codigos):
    print("Insertando codigos de ingles...")
    for i, codigo in enumerate(codigos, start=1):
        cursor.execute(
            "INSERT IGNORE INTO codigos_ingles (materia_codigo, nivel_ingles) VALUES (%s, %s)",
            (codigo, i),
        )
    print(f"  {len(codigos)} codigos OK")


# -- Main -----------------------------------------------------
def main():
    print("\n=== MIGRACION DE PROGRAMAS A MySQL ===\n")
    conn = get_conn()
    cursor = conn.cursor()

    try:
        crear_tablas(cursor)
        conn.commit()

        catalogo = recopilar_materias(PROGRAMAS_DATA)

        insertar_programas(cursor, PROGRAMAS_DATA)
        insertar_materias(cursor, catalogo)
        insertar_programa_materia(cursor, PROGRAMAS_DATA)
        insertar_grupos_electivas(cursor, PROGRAMAS_DATA)
        insertar_codigos_ingles(cursor, CODIGOS_INGLES)

        conn.commit()
        print("\nMigracion completada exitosamente.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
