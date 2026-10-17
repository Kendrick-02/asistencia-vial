# Nexus Vial · Asistencia vial inteligente con agentes de IA

Aplicación web que ayuda a un conductor con un problema en su vehículo dentro de la ciudad (caso configurado para **Bogotá, Colombia**). El usuario describe el problema, adjunta una foto e indica dónde está. El sistema analiza el caso con IA multimodal, ubica el origen con un servicio de mapas, busca servicios cercanos (datos propios + datos reales), calcula rutas y tiempos, y permite registrar una solicitud de asistencia y consultar el caso mediante un chat contextual.

> Proyecto de la Unidad III — Solución inteligente multimodal con herramientas, geolocalización y agentes.

**Autor:** _(Andrea Camila Rodriguez)_

---

## 1. Alcance

- **Usuarios:** conductores particulares (carro o moto) que sufren una falla o necesitan un servicio vehicular.
- **Servicios cubiertos:** talleres, grúas, llantas, combustible/carga eléctrica.
- **Funcionalidades:**
  1. Entrada multimodal: texto + imagen + ubicación de origen.
  2. Análisis con IA y salida estructurada (JSON validado).
  3. Detección de información insuficiente, contradictoria o imagen no relacionada.
  4. Búsqueda en datos propios y en Geoapify, con distancia y tiempo por ruta.
  5. Recomendación basada únicamente en datos consultados.
  6. Registro de una solicitud de asistencia con aprobación del usuario.
  7. Chat contextual por caso con herramientas.
  8. Historial persistente y trazabilidad de agentes y herramientas.

## 2. Arquitectura

```
┌──────────────┐   HTTP    ┌────────────────────────────────────────────┐
│  Frontend    │ ────────► │  Backend FastAPI                           │
│  React+Vite  │ ◄──────── │                                            │
└──────────────┘           │  Orquestador LangGraph (flujo condicional) │
                           │   ┌─────────────┐                          │
                           │   │ A. Analista │──► Gemini (texto+imagen) │
                           │   └──────┬──────┘                          │
                           │  info insuficiente? ──► FIN (pide datos)   │
                           │   ┌──────▼──────┐                          │
                           │   │ B. Ubicación│──► Geoapify Geocoding    │
                           │   └──────┬──────┘                          │
                           │  no se ubicó? ──► FIN                      │
                           │   ┌──────▼──────────┐   ┌───────────────┐  │
                           │   │ C. Recomendador │──►│ SQLite        │  │
                           │   └─────────────────┘   │ servicios     │  │
                           │     │  Geoapify Places  │ casos         │  │
                           │     │  Geoapify Routing │ trazas        │  │
                           │     └► Gemini           │ solicitudes   │  │
                           │                         └───────────────┘  │
                           │  Chat contextual (Gemini + 2 herramientas) │
                           └────────────────────────────────────────────┘
```

| Componente | Tecnología |
|---|---|
| Interfaz web | React + Vite (`frontend/`) |
| Backend | FastAPI (`backend/`) |
| Modelo de IA | Google Gemini (multimodal, salida JSON estructurada, function calling) |
| Datos propios | SQLite (`asistencia_vial.db`) |
| Servicio de mapas | Geoapify (Geocoding, Places, Routing) |
| Orquestación | LangGraph |

### Agentes

| Agente | Responsabilidad | Recibe | Herramientas | Produce |
|---|---|---|---|---|
| **Analista** | Interpretar el caso y decidir si hay información suficiente | Descripción, imagen, ubicación (texto) | Gemini multimodal | `AnalisisNecesidad` (JSON) |
| **Ubicación** | Convertir el origen en coordenadas | Texto de ubicación | Geoapify Geocoding | Coordenadas y dirección resuelta |
| **Recomendador** | Encontrar y comparar servicios y recomendar | Análisis + coordenadas | `consultar_servicios_db`, Geoapify Places, Geoapify Routing, Gemini | Opciones con distancia/tiempo y `Recomendacion` (JSON) |

**Coordinación:** el grafo de LangGraph es condicional. Tras el Analista, si `informacion_suficiente` es falso o `imagen_corresponde` es falso, el flujo termina y se pide más información. Tras el agente de Ubicación, si no se resolvió el origen, el flujo termina. Solo si ambos pasos son válidos participa el Recomendador. El estado compartido acumula las trazas de cada agente.

### Herramientas y acciones

| Nombre | Tipo | Descripción |
|---|---|---|
| `consultar_servicios_db` | Datos propios | Servicios de la BD ordenados por cercanía |
| `geocodificar` | Servicio externo | Dirección → coordenadas (Geoapify) |
| `buscar_lugares_cercanos` | Servicio externo | Establecimientos reales cercanos (Geoapify Places) |
| `calcular_ruta` | Servicio externo | Distancia y tiempo por vía (Geoapify Routing) |
| `crear_solicitud` | **Acción** | Inserta una solicitud en SQLite, ligada al caso; requiere clic del usuario |

El chat contextual puede invocar `consultar_servicios_propios` y `buscar_lugares_en_mapa` (function calling de Gemini).

### Respuesta estructurada

`AnalisisNecesidad`: `observacion`, `tipo_necesidad`, `categoria_servicio`, `posible_causa`, `urgencia` (baja/media/alta), `imagen_corresponde`, `informacion_suficiente`, `datos_faltantes`, `inconsistencias`, `accion_recomendada`.

### Persistencia y trazabilidad

Tablas SQLite: `servicios` (datos propios), `casos` (entrada, análisis, opciones y recomendación), `trazas` (agente, herramienta y detalle de cada paso, incluidas las del chat y la acción) y `solicitudes`. Cualquier caso se recupera con `GET /casos/{id}` o desde el historial de la interfaz.

### Control de alucinaciones

Los prompts prohíben inventar precios, teléfonos, horarios o disponibilidad; la recomendación se genera solo a partir de las opciones consultadas, y los datos no verificados se muestran como tales. El analista distingue observaciones de hipótesis.

## 3. Justificación técnica

- **Gemini:** soporta imagen + texto en una sola llamada, salida JSON con esquema y function calling, tiene capa gratuita y baja latencia en los modelos «flash».
- **Geoapify:** una sola API cubre geocodificación, lugares y rutas; plan gratuito de 3.000 créditos diarios sin tarjeta.
- **LangGraph:** permite aristas condicionales y estado compartido, lo que da una orquestación real y no una cadena fija de prompts.
- **SQLite:** persistencia sin servidor adicional, suficiente para el alcance.

## 4. Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/analizar-caso` | Ejecuta el flujo de agentes y guarda el caso |
| GET | `/casos` | Historial |
| GET | `/casos/{id}` | Detalle con trazabilidad y solicitud |
| POST | `/casos/{id}/solicitud` | Acción: registrar solicitud |
| POST | `/casos/{id}/chat` | Chat contextual del caso |
| GET | `/servicios` | Datos propios |

## 5. Instalación y ejecución

**Requisitos:** Python 3.10 a 3.12 (probado con 3.12; con versiones más nuevas, como 3.15, falla la instalación de dependencias), Node.js 18+, clave de Gemini y clave de Geoapify.

### Backend

```bash
cd backend
py -3.12 -m pip install -r requirements.txt     # Linux/Mac: python3 -m pip install -r requirements.txt
copy .env.example .env                          # Linux/Mac: cp .env.example .env
# edita .env con tus claves de Gemini y Geoapify
py -3.12 -m uvicorn main:app --reload           # Linux/Mac: python3 -m uvicorn main:app --reload
```

`py -3.12` indica a Windows que use Python 3.12 aunque haya otras versiones instaladas. Si se prefiere un entorno virtual, créese antes con `py -3.12 -m venv venv`, actívelo con `venv\Scripts\activate` (en Linux/Mac: `source venv/bin/activate`) y use `python` en lugar de `py -3.12`.

API en `http://127.0.0.1:8000` (documentación en `/docs`). La base `asistencia_vial.db` se crea y se llena con servicios de ejemplo al primer arranque.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

En PowerShell, si aparece el error «la ejecución de scripts está deshabilitada», use `npm.cmd install` y `npm.cmd run dev`.

Abrir `http://localhost:5173`.

## 6. Variables de entorno

Ver `.env`: `GEMINI_API_KEY`, `GEOAPIFY_API_KEY`, `CIUDAD_BASE`.

## 7. Limitaciones

- Los servicios de la tabla `servicios` son **datos de ejemplo** (nombres «Demo»); deben reemplazarse por datos reales para uso productivo.
- Los resultados de Geoapify Places dependen de la cobertura de OpenStreetMap en la zona.
- El sistema no verifica disponibilidad ni costos de los servicios.
- No hay autenticación de usuarios.
