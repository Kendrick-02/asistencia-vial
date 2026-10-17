import json
import sqlite3

DB_NAME = "asistencia_vial.db"


def conectar():
    conexion = sqlite3.connect(DB_NAME)
    conexion.row_factory = sqlite3.Row
    return conexion


# ==================================================
# DATOS PROPIOS DE EJEMPLO (reemplazar por reales)
# nombre, categoria, direccion, lat, lon, telefono,
# horario, servicio_24h
# ==================================================

SERVICIOS_EJEMPLO = [
    ("Taller Demo Chapinero", "taller", "Cra 13 con Cll 60, Chapinero", 4.6486, -74.0628, "601-000-0001", "Lun-Sáb 8:00-18:00", 0),
    ("Taller Demo Kennedy", "taller", "Av. Américas con Cra 78, Kennedy", 4.6280, -74.1450, "601-000-0002", "Lun-Sáb 7:30-17:30", 0),
    ("Taller Demo Usaquén 24h", "taller", "Autopista Norte con Cll 119", 4.6970, -74.0450, "601-000-0003", "24 horas", 1),
    ("Grúas Demo Centro", "grua", "Cll 26 con Cra 30", 4.6430, -74.0800, "601-000-0004", "24 horas", 1),
    ("Grúas Demo Norte", "grua", "Cll 100 con Cra 15", 4.6850, -74.0550, "601-000-0005", "24 horas", 1),
    ("Grúas Demo Sur", "grua", "Autopista Sur con Cll 40 Sur", 4.5950, -74.1300, "601-000-0006", "6:00-22:00", 0),
    ("Llantas Demo Fontibón", "llantas", "Cll 17 con Cra 100, Fontibón", 4.6700, -74.1400, "601-000-0007", "Lun-Sáb 8:00-18:00", 0),
    ("Llantas Demo Suba", "llantas", "Av. Suba con Cll 127", 4.7150, -74.0700, "601-000-0008", "Lun-Dom 7:00-19:00", 0),
    ("Estación Demo Calle 80", "gasolina_o_carga", "Av. Calle 80 con Cra 70", 4.7180, -74.0900, "601-000-0009", "24 horas", 1),
    ("Estación Demo Carrera 7", "gasolina_o_carga", "Cra 7 con Cll 72", 4.6570, -74.0580, "601-000-0010", "24 horas", 1),
]


def inicializar_bd():
    with conectar() as conexion:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS servicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                categoria TEXT NOT NULL,
                direccion TEXT,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                telefono TEXT,
                horario TEXT,
                servicio_24h INTEGER DEFAULT 0
            )
        """)

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS casos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                descripcion TEXT NOT NULL,
                ubicacion_texto TEXT NOT NULL,
                lat REAL,
                lon REAL,
                direccion_resuelta TEXT,
                imagen_nombre TEXT,
                estado TEXT NOT NULL,
                mensaje TEXT,
                analisis_json TEXT,
                opciones_json TEXT,
                recomendacion_json TEXT,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS trazas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caso_id INTEGER NOT NULL,
                agente TEXT NOT NULL,
                herramienta TEXT,
                detalle TEXT,
                fecha TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (caso_id) REFERENCES casos(id)
            )
        """)

        conexion.execute("""
            CREATE TABLE IF NOT EXISTS solicitudes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caso_id INTEGER NOT NULL,
                servicio_nombre TEXT NOT NULL,
                tipo_servicio TEXT,
                notas TEXT,
                estado TEXT DEFAULT 'Registrada',
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (caso_id) REFERENCES casos(id)
            )
        """)

        total = conexion.execute(
            "SELECT COUNT(*) AS n FROM servicios"
        ).fetchone()["n"]

        if total == 0:
            conexion.executemany(
                """
                INSERT INTO servicios
                    (nombre, categoria, direccion, lat, lon,
                     telefono, horario, servicio_24h)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                SERVICIOS_EJEMPLO
            )


# ==================================================
# CASOS Y TRAZAS
# ==================================================

def guardar_caso(
    descripcion,
    ubicacion_texto,
    coordenadas,
    imagen_nombre,
    estado,
    mensaje,
    analisis,
    opciones,
    recomendacion
) -> int:

    coordenadas = coordenadas or {}

    with conectar() as conexion:
        cursor = conexion.execute(
            """
            INSERT INTO casos
                (descripcion, ubicacion_texto, lat, lon,
                 direccion_resuelta, imagen_nombre, estado,
                 mensaje, analisis_json, opciones_json,
                 recomendacion_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                descripcion,
                ubicacion_texto,
                coordenadas.get("lat"),
                coordenadas.get("lon"),
                coordenadas.get("direccion"),
                imagen_nombre,
                estado,
                mensaje,
                json.dumps(analisis or {}, ensure_ascii=False),
                json.dumps(opciones or [], ensure_ascii=False),
                json.dumps(recomendacion or {}, ensure_ascii=False),
            )
        )
        return cursor.lastrowid


def guardar_trazas(caso_id: int, trazas: list):
    with conectar() as conexion:
        conexion.executemany(
            """
            INSERT INTO trazas (caso_id, agente, herramienta, detalle)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    caso_id,
                    t.get("agente", ""),
                    t.get("herramienta", ""),
                    t.get("detalle", ""),
                )
                for t in trazas
            ]
        )


def agregar_traza(caso_id, agente, herramienta, detalle):
    guardar_trazas(
        caso_id,
        [{"agente": agente, "herramienta": herramienta, "detalle": detalle}]
    )


def _fila_a_caso(fila) -> dict:
    return {
        "caso_id": fila["id"],
        "codigo": f"CASO-{fila['id']:03d}",
        "descripcion": fila["descripcion"],
        "ubicacion_texto": fila["ubicacion_texto"],
        "coordenadas": (
            {
                "lat": fila["lat"],
                "lon": fila["lon"],
                "direccion": fila["direccion_resuelta"],
            }
            if fila["lat"] is not None
            else {}
        ),
        "imagen_nombre": fila["imagen_nombre"],
        "estado": fila["estado"],
        "mensaje": fila["mensaje"],
        "analisis": json.loads(fila["analisis_json"] or "{}"),
        "opciones": json.loads(fila["opciones_json"] or "[]"),
        "recomendacion": json.loads(fila["recomendacion_json"] or "{}"),
        "fecha_creacion": fila["fecha_creacion"],
    }


def obtener_caso(caso_id: int):
    with conectar() as conexion:
        fila = conexion.execute(
            "SELECT * FROM casos WHERE id = ?", (caso_id,)
        ).fetchone()

        if not fila:
            return None

        caso = _fila_a_caso(fila)

        trazas = conexion.execute(
            """
            SELECT agente, herramienta, detalle, fecha
            FROM trazas WHERE caso_id = ? ORDER BY id
            """,
            (caso_id,)
        ).fetchall()

        solicitud = conexion.execute(
            """
            SELECT id, servicio_nombre, tipo_servicio, notas,
                   estado, fecha_creacion
            FROM solicitudes WHERE caso_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (caso_id,)
        ).fetchone()

    caso["trazabilidad"] = [dict(t) for t in trazas]
    caso["solicitud"] = _solicitud_a_dict(solicitud)
    return caso


def listar_casos() -> list:
    with conectar() as conexion:
        filas = conexion.execute(
            """
            SELECT c.*, s.id AS solicitud_id,
                   s.servicio_nombre AS solicitud_servicio
            FROM casos c
            LEFT JOIN solicitudes s ON s.caso_id = c.id
            ORDER BY c.id DESC
            """
        ).fetchall()

    resultado = []
    for fila in filas:
        caso = _fila_a_caso(fila)
        analisis = caso["analisis"]
        resultado.append({
            "caso_id": caso["caso_id"],
            "codigo": caso["codigo"],
            "ubicacion_texto": caso["ubicacion_texto"],
            "necesidad": analisis.get("tipo_necesidad", "—"),
            "urgencia": analisis.get("urgencia", ""),
            "estado": caso["estado"],
            "solicitud": fila["solicitud_servicio"],
            "fecha_creacion": caso["fecha_creacion"],
        })
    return resultado


# ==================================================
# SOLICITUDES (ACCIÓN QUE CAMBIA EL SISTEMA)
# ==================================================

def _solicitud_a_dict(fila):
    if not fila:
        return None
    return {
        "solicitud": f"SOL-{fila['id']:03d}",
        "servicio_nombre": fila["servicio_nombre"],
        "tipo_servicio": fila["tipo_servicio"],
        "notas": fila["notas"],
        "estado": fila["estado"],
        "fecha_creacion": fila["fecha_creacion"],
    }


def crear_solicitud(caso_id, servicio_nombre, tipo_servicio, notas) -> dict:
    with conectar() as conexion:
        cursor = conexion.execute(
            """
            INSERT INTO solicitudes
                (caso_id, servicio_nombre, tipo_servicio, notas)
            VALUES (?, ?, ?, ?)
            """,
            (caso_id, servicio_nombre, tipo_servicio, notas)
        )
        fila = conexion.execute(
            "SELECT * FROM solicitudes WHERE id = ?",
            (cursor.lastrowid,)
        ).fetchone()

    return _solicitud_a_dict(fila)
