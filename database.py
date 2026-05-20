# database.py
import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

load_dotenv()

# Railway provee MYSQLHOST, MYSQLUSER, MYSQLPASSWORD, MYSQLDATABASE, MYSQLPORT.
# Localmente se usan DB_HOST, DB_USER, DB_PASSWORD, DB_NAME, DB_PORT.
# Se intenta Railway primero; si no existe, cae al valor local.
DB_CONFIG = {
    'host':     os.getenv('MYSQLHOST')     or os.getenv('DB_HOST',     'localhost'),
    'user':     os.getenv('MYSQLUSER')     or os.getenv('DB_USER',     'root'),
    'password': os.getenv('MYSQLPASSWORD') or os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('MYSQLDATABASE') or os.getenv('DB_NAME',     'duoprogram_db'),
    'port': int(os.getenv('MYSQLPORT')     or os.getenv('DB_PORT',     3306)),
}

def get_db_connection():
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        print(f"Error conectando a MySQL: {e}")
        return None

def init_db():
    # En Railway la BD ya existe y el usuario no tiene permisos para crearla.
    # Se intenta la conexion directa; si falla, se aborta sin romper el servidor.
    connection = get_db_connection()
    if not connection:
        print("No se pudo conectar a la base de datos")
        return

    cursor = connection.cursor()

    # Solo intentar CREATE DATABASE en entorno local (host = localhost)
    if DB_CONFIG['host'] == 'localhost':
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}")
        cursor.execute(f"USE {DB_CONFIG['database']}")

    # Crear tabla de usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            nombre_completo VARCHAR(200) NOT NULL,
            email VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Crear tabla de planes guardados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS planes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NOT NULL,
            nombre VARCHAR(120) DEFAULT NULL,
            programa_principal VARCHAR(10) NOT NULL,
            programa_secundario VARCHAR(10),
            semestres_cursados INT,
            promedio DECIMAL(3,1),
            materias_aprobadas JSON,
            homologaciones JSON,
            plan_generado JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    # Agregar columna nombre si no existe (para instalaciones previas sin ella)
    try:
        cursor.execute("ALTER TABLE planes ADD COLUMN nombre VARCHAR(120) DEFAULT NULL")
        connection.commit()
    except Exception:
        pass  # La columna ya existe

    # Crear tabla de historial
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historial (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NOT NULL,
            accion VARCHAR(100) NOT NULL,
            detalles TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
        )
    """)

    connection.commit()
    cursor.close()
    connection.close()
    print("Base de datos inicializada correctamente")
