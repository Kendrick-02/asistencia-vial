import json
import operator
from typing import Annotated, Literal, TypedDict

from google.genai import types
from langgraph.graph import StateGraph, START, END
from pydantic import BaseModel

from herramientas import (
    consultar_servicios_db,
    buscar_lugares_cercanos,
    geocodificar,
    calcular_ruta,
)


# ==================================================
# ESQUEMAS DE RESPUESTA ESTRUCTURADA
# ==================================================

class AnalisisNecesidad(BaseModel):
    observacion: str
    tipo_necesidad: str
    categoria_servicio: Literal[
        "taller", "grua", "llantas", "gasolina_o_carga", "otro"
    ]
    posible_causa: str
    urgencia: Literal["baja", "media", "alta"]
    imagen_corresponde: bool
    informacion_suficiente: bool
    datos_faltantes: str
    inconsistencias: str
    accion_recomendada: str


class Recomendacion(BaseModel):
    servicio_sugerido: str
    justificacion: str
    advertencias: str


# ==================================================
# ESTADO COMPARTIDO ENTRE LOS AGENTES
# ==================================================

class EstadoCaso(TypedDict):
    descripcion: str
    ubicacion_texto: str
    imagen_bytes: bytes
    mime_type: str

    analisis: dict
    coordenadas: dict
    opciones: list
    recomendacion: dict
    estado: str
    mensaje: str
    # Las trazas se acumulan: cada agente agrega las suyas
    trazas: Annotated[list, operator.add]


# ==================================================
# ORQUESTADOR
# ==================================================

def crear_orquestador(cliente, modelo):

    # ----------------------------------------------
    # AGENTE 1: ANALISTA (Gemini multimodal)
    # Recibe: texto + imagen. No usa herramientas externas.
    # Produce: AnalisisNecesidad (JSON estructurado) y
    #          decide si la información alcanza.
    # ----------------------------------------------
    def agente_analista(estado: EstadoCaso):

        prompt = f"""
        Eres un agente analista de asistencia vial en una ciudad.

        Descripción del usuario:
        {estado["descripcion"]}

        Ubicación indicada por el usuario:
        {estado["ubicacion_texto"]}

        Analiza la descripción y la imagen adjunta.

        Determina:
        - observacion: qué se observa realmente en la imagen.
        - tipo_necesidad: por ejemplo "llanta ponchada",
          "falla de motor", "batería descargada", "sin combustible".
        - categoria_servicio: taller, grua, llantas,
          gasolina_o_carga u otro.
        - posible_causa: hipótesis, no hechos confirmados.
        - urgencia: baja, media o alta.
        - imagen_corresponde: false si la imagen no tiene relación
          con un vehículo o con el problema descrito.
        - informacion_suficiente: false si la descripción es tan
          vaga que no se puede saber qué servicio necesita.
        - datos_faltantes: qué debe aclarar el usuario
          (escribe "Ninguno" si nada).
        - inconsistencias: contradicciones entre texto e imagen
          (escribe "Ninguna" si no hay).
        - accion_recomendada: siguiente paso para el usuario.

        CRITERIOS DE URGENCIA:
        ALTA: riesgo de seguridad (humo, fuego, accidente, vehículo
        detenido en vía rápida, heridos).
        MEDIA: vehículo inmovilizado sin riesgo inmediato.
        BAJA: revisión preventiva o situación no urgente.

        REGLAS:
        - No inventes datos ni causas confirmadas.
        - Distingue lo observado de las hipótesis.
        - Si hay heridos o riesgo inmediato, incluye en la acción
          recomendada llamar a la línea de emergencias 123.
        - No elijas talleres ni grúas: eso lo hace otro agente.
        """

        respuesta = cliente.models.generate_content(
            model=modelo,
            contents=[
                types.Part.from_bytes(
                    data=estado["imagen_bytes"],
                    mime_type=estado["mime_type"],
                ),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=AnalisisNecesidad,
            ),
        )

        resultado = AnalisisNecesidad.model_validate_json(respuesta.text)
        analisis = resultado.model_dump()

        cambios = {
            "analisis": analisis,
            "trazas": [{
                "agente": "Agente analista",
                "herramienta": "Gemini multimodal",
                "detalle": (
                    f"Necesidad: {analisis['tipo_necesidad']} · "
                    f"urgencia {analisis['urgencia']} · "
                    f"info suficiente: {analisis['informacion_suficiente']}"
                ),
            }],
        }

        if not analisis["informacion_suficiente"] or not analisis["imagen_corresponde"]:
            partes = []
            if not analisis["informacion_suficiente"]:
                partes.append(f"Falta información: {analisis['datos_faltantes']}")
            if not analisis["imagen_corresponde"]:
                partes.append("La imagen no corresponde con el caso descrito.")
            if analisis["inconsistencias"].strip().lower() not in ("ninguna", "ninguna.", "n/a", ""):
                partes.append(f"Inconsistencias: {analisis['inconsistencias']}")

            cambios["estado"] = "requiere_informacion"
            cambios["mensaje"] = " ".join(partes)

        return cambios

    # ----------------------------------------------
    # AGENTE 2: UBICACIÓN
    # Recibe: texto de ubicación.
    # Herramienta: Geoapify Geocoding.
    # Produce: coordenadas.
    # ----------------------------------------------
    def agente_ubicacion(estado: EstadoCaso):

        resultado = geocodificar(estado["ubicacion_texto"])

        if "error" in resultado:
            return {
                "estado": "ubicacion_no_encontrada",
                "mensaje": (
                    "No fue posible ubicar el origen indicado. "
                    f"Detalle: {resultado['error']}"
                ),
                "trazas": [{
                    "agente": "Agente de ubicación",
                    "herramienta": "Geoapify Geocoding",
                    "detalle": f"Error: {resultado['error']}",
                }],
            }

        return {
            "coordenadas": resultado,
            "trazas": [{
                "agente": "Agente de ubicación",
                "herramienta": "Geoapify Geocoding",
                "detalle": f"Origen resuelto: {resultado['direccion']}",
            }],
        }

    # ----------------------------------------------
    # AGENTE 3: RECOMENDADOR
    # Recibe: análisis + coordenadas.
    # Herramientas: BD propia, Geoapify Places y Routing.
    # Produce: opciones con distancia/tiempo y una
    #          recomendación basada solo en esos datos.
    # ----------------------------------------------
    def agente_recomendador(estado: EstadoCaso):

        analisis = estado["analisis"]
        coords = estado["coordenadas"]
        lat, lon = coords["lat"], coords["lon"]
        categoria = analisis["categoria_servicio"]

        trazas = []
        candidatos = []

        # --- Herramienta de datos propios ---
        propios = consultar_servicios_db(categoria, lat, lon)
        for p in propios:
            candidatos.append({**p, "fuente": "datos_propios"})
        trazas.append({
            "agente": "Agente recomendador",
            "herramienta": "consultar_servicios_db",
            "detalle": f"{len(propios)} servicios propios de categoría '{categoria}'",
        })

        # --- Herramienta externa: lugares cercanos ---
        advertencias_tools = []
        externos = buscar_lugares_cercanos(categoria, lat, lon)
        if isinstance(externos, dict) and "error" in externos:
            advertencias_tools.append(externos["error"])
            trazas.append({
                "agente": "Agente recomendador",
                "herramienta": "Geoapify Places",
                "detalle": f"Error: {externos['error']}",
            })
        else:
            for e in externos:
                candidatos.append({**e, "fuente": "geoapify"})
            trazas.append({
                "agente": "Agente recomendador",
                "herramienta": "Geoapify Places",
                "detalle": f"{len(externos)} lugares reales cercanos",
            })

        candidatos.sort(key=lambda c: c["distancia_directa_km"])
        opciones = candidatos[:4]

        # --- Herramienta externa: rutas ---
        rutas_ok = 0
        for op in opciones:
            ruta = calcular_ruta(lat, lon, op["lat"], op["lon"])
            if "error" in ruta:
                op["distancia_ruta_km"] = None
                op["tiempo_min"] = None
            else:
                op.update(ruta)
                rutas_ok += 1
        trazas.append({
            "agente": "Agente recomendador",
            "herramienta": "Geoapify Routing",
            "detalle": f"Rutas calculadas para {rutas_ok} de {len(opciones)} opciones",
        })

        opciones.sort(
            key=lambda o: (o["tiempo_min"] is None, o["tiempo_min"] or 0, o["distancia_directa_km"])
        )

        if not opciones:
            return {
                "opciones": [],
                "recomendacion": {
                    "servicio_sugerido": "Ninguno",
                    "justificacion": "No se encontraron servicios cercanos en las fuentes consultadas.",
                    "advertencias": " ".join(advertencias_tools),
                },
                "estado": "completado",
                "mensaje": "Análisis completado sin opciones cercanas",
                "trazas": trazas,
            }

        # --- Redacción de la recomendación (solo con datos reales) ---
        prompt = f"""
        Eres un agente recomendador de asistencia vial.

        Análisis del caso:
        {json.dumps(analisis, ensure_ascii=False)}

        Opciones encontradas (datos propios y Geoapify), ya ordenadas
        por tiempo estimado de llegada:
        {json.dumps(opciones, ensure_ascii=False)}

        Elige la opción más adecuada y justifícala.

        REGLAS:
        - Usa únicamente los datos de las opciones. No inventes
          precios, teléfonos, horarios ni disponibilidad.
        - Si un dato es nulo, di que no está verificado.
        - Si la urgencia es alta, prioriza la rapidez.
        - servicio_sugerido debe ser exactamente el nombre de una opción.
        - En advertencias menciona lo que el usuario debe confirmar
          por teléfono (disponibilidad, costo).
        """

        respuesta = cliente.models.generate_content(
            model=modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Recomendacion,
            ),
        )
        rec = Recomendacion.model_validate_json(respuesta.text).model_dump()

        if advertencias_tools:
            rec["advertencias"] += " Nota: " + " ".join(advertencias_tools)

        trazas.append({
            "agente": "Agente recomendador",
            "herramienta": "Gemini",
            "detalle": f"Recomendación: {rec['servicio_sugerido']}",
        })

        return {
            "opciones": opciones,
            "recomendacion": rec,
            "estado": "completado",
            "mensaje": "Análisis completado",
            "trazas": trazas,
        }

    # ----------------------------------------------
    # ORQUESTACIÓN CONDICIONAL CON LANGGRAPH
    # ----------------------------------------------
    def decidir_tras_analisis(estado: EstadoCaso):
        # Si la información es insuficiente/contradictoria, se detiene.
        return "fin" if estado.get("estado") == "requiere_informacion" else "ubicacion"

    def decidir_tras_ubicacion(estado: EstadoCaso):
        return "recomendador" if estado.get("coordenadas") else "fin"

    grafo = StateGraph(EstadoCaso)

    grafo.add_node("analista", agente_analista)
    grafo.add_node("ubicacion", agente_ubicacion)
    grafo.add_node("recomendador", agente_recomendador)

    grafo.add_edge(START, "analista")
    grafo.add_conditional_edges(
        "analista",
        decidir_tras_analisis,
        {"ubicacion": "ubicacion", "fin": END},
    )
    grafo.add_conditional_edges(
        "ubicacion",
        decidir_tras_ubicacion,
        {"recomendador": "recomendador", "fin": END},
    )
    grafo.add_edge("recomendador", END)

    return grafo.compile()
