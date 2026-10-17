"""
Herramientas disponibles para los agentes y el chat.

1. consultar_servicios_db   -> datos propios (SQLite)
2. buscar_lugares_cercanos  -> servicio externo (Geoapify Places)
3. geocodificar             -> servicio externo (Geoapify Geocoding)
4. calcular_ruta            -> servicio externo (Geoapify Routing)

La acción que cambia el sistema (crear_solicitud) está en database.py.
"""

import math
import os

import requests

from database import conectar

GEOAPIFY_URL = "https://api.geoapify.com"
TIMEOUT = 10

# Categoría interna -> categoría de Geoapify Places.
# Verifica los nombres en la documentación de Geoapify si cambian.
CATEGORIAS_GEOAPIFY = {
    "taller": "service.vehicle.car_repair",
    "grua": "service.vehicle",
    "llantas": "service.vehicle",
    "gasolina_o_carga": "service.vehicle.charging_station,commercial.gas",
    "otro": "service.vehicle",
}


def _api_key():
    return os.getenv("GEOAPIFY_API_KEY")


def _distancia_km(lat1, lon1, lat2, lon2) -> float:
    """Distancia en línea recta (haversine)."""
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * r * math.asin(math.sqrt(a)), 2)


# ==================================================
# HERRAMIENTA 1: DATOS PROPIOS
# ==================================================

def consultar_servicios_db(
    categoria: str,
    lat: float,
    lon: float,
    limite: int = 5
) -> list:
    """Consulta los servicios registrados en la base de datos propia,
    ordenados por cercanía al punto dado.

    Args:
        categoria: taller, grua, llantas, gasolina_o_carga u otro.
        lat: latitud del origen.
        lon: longitud del origen.
        limite: máximo de resultados.
    """
    with conectar() as conexion:
        if categoria == "otro":
            filas = conexion.execute("SELECT * FROM servicios").fetchall()
        else:
            filas = conexion.execute(
                "SELECT * FROM servicios WHERE categoria = ?", (categoria,)
            ).fetchall()

    servicios = [
        {
            "nombre": f["nombre"],
            "categoria": f["categoria"],
            "direccion": f["direccion"],
            "lat": f["lat"],
            "lon": f["lon"],
            "telefono": f["telefono"],
            "horario": f["horario"],
            "servicio_24h": bool(f["servicio_24h"]),
            "distancia_directa_km": _distancia_km(lat, lon, f["lat"], f["lon"]),
        }
        for f in filas
    ]
    servicios.sort(key=lambda s: s["distancia_directa_km"])
    return servicios[:limite]


# ==================================================
# HERRAMIENTA 2: GEOCODIFICACIÓN (GEOAPIFY)
# ==================================================

def geocodificar(texto: str) -> dict:
    """Convierte una dirección o barrio en coordenadas."""
    if not _api_key():
        return {"error": "Falta GEOAPIFY_API_KEY en el archivo .env"}

    ciudad = os.getenv("CIUDAD_BASE", "Bogotá, Colombia")
    consulta = texto if ciudad.split(",")[0].lower() in texto.lower() else f"{texto}, {ciudad}"

    try:
        r = requests.get(
            f"{GEOAPIFY_URL}/v1/geocode/search",
            params={
                "text": consulta,
                "filter": "countrycode:co",
                "limit": 1,
                "apiKey": _api_key(),
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        features = r.json().get("features", [])
    except requests.RequestException as e:
        return {"error": f"Fallo al consultar Geoapify: {e}"}

    if not features:
        return {"error": "No se encontró la ubicación indicada"}

    p = features[0]["properties"]
    return {
        "lat": p["lat"],
        "lon": p["lon"],
        "direccion": p.get("formatted", texto),
    }


# ==================================================
# HERRAMIENTA 3: LUGARES CERCANOS (GEOAPIFY)
# ==================================================

def buscar_lugares_cercanos(
    categoria: str,
    lat: float,
    lon: float,
    radio_m: int = 5000,
    limite: int = 5
):
    """Busca establecimientos reales cerca de un punto usando Geoapify.

    Args:
        categoria: taller, grua, llantas, gasolina_o_carga u otro.
        lat: latitud del origen.
        lon: longitud del origen.
        radio_m: radio de búsqueda en metros.
        limite: máximo de resultados.
    """
    if not _api_key():
        return {"error": "Falta GEOAPIFY_API_KEY en el archivo .env"}

    try:
        r = requests.get(
            f"{GEOAPIFY_URL}/v2/places",
            params={
                "categories": CATEGORIAS_GEOAPIFY.get(categoria, "service.vehicle"),
                "filter": f"circle:{lon},{lat},{radio_m}",
                "bias": f"proximity:{lon},{lat}",
                "limit": limite * 2,
                "apiKey": _api_key(),
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        features = r.json().get("features", [])
    except requests.RequestException as e:
        return {"error": f"Fallo al consultar Geoapify: {e}"}

    lugares = []
    for f in features:
        p = f["properties"]
        if not p.get("name"):
            continue
        lugares.append({
            "nombre": p["name"],
            "categoria": categoria,
            "direccion": p.get("address_line2") or p.get("formatted"),
            "lat": p["lat"],
            "lon": p["lon"],
            "telefono": (p.get("contact") or {}).get("phone"),
            "horario": p.get("opening_hours"),
            "distancia_directa_km": _distancia_km(lat, lon, p["lat"], p["lon"]),
        })

    lugares.sort(key=lambda x: x["distancia_directa_km"])
    return lugares[:limite]


# ==================================================
# HERRAMIENTA 4: RUTA Y TIEMPO (GEOAPIFY)
# ==================================================

def calcular_ruta(lat_origen: float, lon_origen: float, lat_destino: float, lon_destino: float) -> dict:
    """Calcula distancia y tiempo de conducción por carretera."""
    if not _api_key():
        return {"error": "Falta GEOAPIFY_API_KEY en el archivo .env"}

    try:
        r = requests.get(
            f"{GEOAPIFY_URL}/v1/routing",
            params={
                "waypoints": f"{lat_origen},{lon_origen}|{lat_destino},{lon_destino}",
                "mode": "drive",
                "apiKey": _api_key(),
            },
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        p = r.json()["features"][0]["properties"]
    except (requests.RequestException, KeyError, IndexError) as e:
        return {"error": f"No se pudo calcular la ruta: {e}"}

    return {
        "distancia_ruta_km": round(p["distance"] / 1000, 2),
        "tiempo_min": round(p["time"] / 60),
    }
