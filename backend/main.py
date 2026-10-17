import os
from typing import Literal

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from google import genai
from google.genai import types, errors

load_dotenv()

from database import (
    inicializar_bd,
    guardar_caso,
    guardar_trazas,
    agregar_traza,
    obtener_caso,
    listar_casos,
    crear_solicitud,
)
from herramientas import consultar_servicios_db, buscar_lugares_cercanos
from agentes import crear_orquestador

# ==================================================
# CONFIGURACIÓN
# ==================================================

inicializar_bd()

app = FastAPI(
    title="Asistencia Vial IA",
    description="Movilidad y servicios urbanos con agentes LangGraph y Geoapify",
    version="4.0",
)

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODELO_IA = os.getenv("MODELO_IA", "gemini-3.1-flash-lite")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orquestador = crear_orquestador(cliente=client, modelo=MODELO_IA)

TIPOS_IMAGEN = {"image/jpeg", "image/png", "image/webp"}


def mensaje_error_ia(error) -> str:
    if isinstance(error, errors.ServerError):
        if error.code == 503:
            return "El servicio de IA está temporalmente saturado. Intenta nuevamente."
        return "El servicio de IA presentó un error."
    if isinstance(error, errors.ClientError):
        if error.code == 429:
            return "Se alcanzó el límite de solicitudes del modelo de IA."
        return "No fue posible procesar la solicitud."
    return "Ocurrió un error durante el procesamiento."


# ==================================================
# ENDPOINTS GENERALES
# ==================================================

@app.get("/")
def inicio():
    return {
        "mensaje": "Asistencia Vial IA funcionando",
        "persistencia": "SQLite",
        "orquestacion": "LangGraph",
        "geolocalizacion": "Geoapify",
        "version": "4.0",
    }


@app.get("/servicios")
def listar_servicios():
    """Datos propios: servicios registrados en la BD."""
    from database import conectar
    with conectar() as conexion:
        filas = conexion.execute("SELECT * FROM servicios ORDER BY categoria, nombre").fetchall()
    return {"total": len(filas), "servicios": [dict(f) for f in filas]}


# ==================================================
# ANÁLISIS ORQUESTADO
# ==================================================

@app.post("/analizar-caso")
async def analizar_caso(
    ubicacion: str = Form(...),
    descripcion: str = Form(...),
    imagen: UploadFile = File(...),
):
    if imagen.content_type not in TIPOS_IMAGEN:
        return {"error": True, "mensaje": "La imagen debe ser JPG, PNG o WEBP."}

    try:
        contenido = await imagen.read()

        estado_inicial = {
            "descripcion": descripcion,
            "ubicacion_texto": ubicacion,
            "imagen_bytes": contenido,
            "mime_type": imagen.content_type,
            "analisis": {},
            "coordenadas": {},
            "opciones": [],
            "recomendacion": {},
            "estado": "",
            "mensaje": "",
            "trazas": [],
        }

        # El grafo es síncrono: se ejecuta en un hilo para no bloquear el servidor
        resultado = await run_in_threadpool(orquestador.invoke, estado_inicial)

        caso_id = guardar_caso(
            descripcion=descripcion,
            ubicacion_texto=ubicacion,
            coordenadas=resultado["coordenadas"],
            imagen_nombre=imagen.filename,
            estado=resultado["estado"],
            mensaje=resultado["mensaje"],
            analisis=resultado["analisis"],
            opciones=resultado["opciones"],
            recomendacion=resultado["recomendacion"],
        )
        guardar_trazas(caso_id, resultado["trazas"])

        return obtener_caso(caso_id)

    except (errors.ServerError, errors.ClientError) as error:
        return {"error": True, "mensaje": mensaje_error_ia(error)}

    except Exception as error:
        print("Error en la orquestación:", repr(error))
        return {"error": True, "mensaje": "Ocurrió un error durante la orquestación."}


# ==================================================
# PERSISTENCIA Y TRAZABILIDAD
# ==================================================

@app.get("/casos")
def historial_casos():
    casos = listar_casos()
    return {"total": len(casos), "casos": casos}


@app.get("/casos/{caso_id}")
def detalle_caso(caso_id: int):
    caso = obtener_caso(caso_id)
    if not caso:
        return {"error": True, "mensaje": "Caso no encontrado"}
    return caso


# ==================================================
# ACCIÓN: REGISTRAR SOLICITUD (APROBACIÓN HUMANA)
# ==================================================

@app.post("/casos/{caso_id}/solicitud")
def registrar_solicitud(
    caso_id: int,
    servicio_nombre: str = Form(...),
    tipo_servicio: Literal["taller", "grua", "llantas", "gasolina_o_carga", "otro"] = Form("otro"),
    notas: str = Form(""),
):
    caso = obtener_caso(caso_id)
    if not caso:
        return {"error": True, "mensaje": "Caso no encontrado"}

    if caso["estado"] != "completado":
        return {"error": True, "mensaje": "El caso no tiene una recomendación completa."}

    if caso["solicitud"]:
        return {"error": True, "mensaje": "Este caso ya tiene una solicitud registrada."}

    solicitud = crear_solicitud(caso_id, servicio_nombre, tipo_servicio, notas)

    agregar_traza(
        caso_id,
        "Acción del sistema",
        "crear_solicitud",
        f"{solicitud['solicitud']} registrada con '{servicio_nombre}' (aprobada por el usuario)",
    )

    return {"mensaje": "Solicitud registrada correctamente", "solicitud": solicitud}


# ==================================================
# CHAT CONTEXTUAL POR CASO (con herramientas)
# ==================================================

@app.post("/casos/{caso_id}/chat")
def chat_caso(caso_id: int, pregunta: str = Form(...)):

    caso = obtener_caso(caso_id)
    if not caso:
        return {"error": True, "mensaje": "Caso no encontrado"}

    coords = caso["coordenadas"]
    usadas = []  # herramientas que el modelo decide invocar

    def consultar_servicios_propios(categoria: str) -> list:
        """Consulta los servicios de la base de datos propia cercanos
        al origen del caso. categoria: taller, grua, llantas,
        gasolina_o_carga u otro."""
        if not coords:
            return [{"error": "El caso no tiene ubicación resuelta"}]
        usadas.append(("consultar_servicios_db", f"categoria={categoria}"))
        return consultar_servicios_db(categoria, coords["lat"], coords["lon"])

    def buscar_lugares_en_mapa(categoria: str) -> list:
        """Busca establecimientos reales cercanos al origen del caso
        usando Geoapify. categoria: taller, grua, llantas,
        gasolina_o_carga u otro."""
        if not coords:
            return [{"error": "El caso no tiene ubicación resuelta"}]
        usadas.append(("Geoapify Places", f"categoria={categoria}"))
        return buscar_lugares_cercanos(categoria, coords["lat"], coords["lon"])

    contexto = {
        "descripcion": caso["descripcion"],
        "ubicacion": caso["ubicacion_texto"],
        "ubicacion_resuelta": coords,
        "estado_del_caso": caso["estado"],
        "analisis": caso["analisis"],
        "opciones_encontradas": caso["opciones"],
        "recomendacion": caso["recomendacion"],
        "solicitud_registrada": caso["solicitud"],
    }

    prompt = f"""
    Eres un asistente de asistencia vial. Responde solo preguntas
    relacionadas con este caso.

    Contexto del caso (datos reales ya consultados):
    {contexto}

    Pregunta del usuario:
    {pregunta}

    REGLAS:
    - Usa el contexto y, si hace falta más información, las
      herramientas disponibles.
    - No presentes como hecho nada que no esté en el contexto o en
      los resultados de las herramientas.
    - No inventes precios, tiempos ni disponibilidad.
    - Si no conoces un dato, dilo.
    - Responde con claridad y brevedad.
    """

    try:
        response = client.models.generate_content(
            model=MODELO_IA,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[consultar_servicios_propios, buscar_lugares_en_mapa]
            ),
        )

        for herramienta, detalle in usadas:
            agregar_traza(caso_id, "Chat contextual", herramienta, detalle)
        agregar_traza(caso_id, "Chat contextual", "Gemini", f"Pregunta: {pregunta[:120]}")

        return {"pregunta": pregunta, "respuesta": response.text}

    except (errors.ServerError, errors.ClientError) as error:
        return {"pregunta": pregunta, "respuesta": mensaje_error_ia(error)}

    except Exception as error:
        print("Error en el chat:", repr(error))
        return {"pregunta": pregunta, "respuesta": "Ocurrió un error inesperado."}
