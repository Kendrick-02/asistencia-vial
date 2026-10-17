import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";
import "./AppExtra.css";

const API = "http://127.0.0.1:8000";

const ETIQUETAS_CATEGORIA = {
  taller: "Taller",
  grua: "Grúa",
  llantas: "Llantas",
  gasolina_o_carga: "Combustible / carga",
  otro: "Otro",
};

function App() {
  const [ubicacion, setUbicacion] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [imagen, setImagen] = useState(null);

  const [caso, setCaso] = useState(null);
  const [cargando, setCargando] = useState(false);
  const [errorAnalisis, setErrorAnalisis] = useState("");

  const [solicitud, setSolicitud] = useState(null);
  const [creandoSolicitud, setCreandoSolicitud] = useState(false);

  const [pregunta, setPregunta] = useState("");
  const [mensajes, setMensajes] = useState([]);
  const [enviandoChat, setEnviandoChat] = useState(false);

  const [historial, setHistorial] = useState([]);
  const [cargandoHistorial, setCargandoHistorial] = useState(false);
  const [errorHistorial, setErrorHistorial] = useState("");

  // ================================================
  // HISTORIAL (SQLite)
  // ================================================

  const cargarHistorial = async () => {
    try {
      setCargandoHistorial(true);
      setErrorHistorial("");

      const respuesta = await fetch(`${API}/casos`);
      if (!respuesta.ok) throw new Error();

      const resultado = await respuesta.json();
      setHistorial(resultado.casos || []);
    } catch {
      setErrorHistorial("No fue posible consultar el historial de casos.");
    } finally {
      setCargandoHistorial(false);
    }
  };

  useEffect(() => {
    cargarHistorial();
  }, []);

  // ================================================
  // RECUPERAR UN CASO GUARDADO
  // ================================================

  const verCaso = async (id) => {
    try {
      const respuesta = await fetch(`${API}/casos/${id}`);
      const detalle = await respuesta.json();

      if (detalle.error) {
        alert(detalle.mensaje);
        return;
      }

      setCaso(detalle);
      setSolicitud(detalle.solicitud || null);
      setMensajes([]);
      setPregunta("");
      setErrorAnalisis("");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      alert("No fue posible recuperar el caso.");
    }
  };

  // ================================================
  // ANÁLISIS ORQUESTADO
  // ================================================

  const analizarCaso = async (e) => {
    e.preventDefault();

    if (!ubicacion.trim() || !descripcion.trim() || !imagen) {
      alert("Indica tu ubicación, describe el problema y selecciona una imagen.");
      return;
    }

    const datos = new FormData();
    datos.append("ubicacion", ubicacion.trim());
    datos.append("descripcion", descripcion.trim());
    datos.append("imagen", imagen);

    setCargando(true);
    setCaso(null);
    setSolicitud(null);
    setMensajes([]);
    setPregunta("");
    setErrorAnalisis("");

    try {
      const respuesta = await fetch(`${API}/analizar-caso`, {
        method: "POST",
        body: datos,
      });

      if (!respuesta.ok) throw new Error("No fue posible analizar el caso.");

      const resultado = await respuesta.json();

      if (resultado.error) {
        setErrorAnalisis(
          resultado.mensaje || "El servicio de IA no pudo completar el análisis."
        );
        return;
      }

      setCaso(resultado);
      await cargarHistorial();
    } catch (error) {
      setErrorAnalisis(
        error.message || "No fue posible conectar con el servicio."
      );
    } finally {
      setCargando(false);
    }
  };

  // ================================================
  // ACCIÓN: REGISTRAR SOLICITUD (APROBACIÓN HUMANA)
  // ================================================

  const registrarSolicitud = async (opcion) => {
    if (!caso || solicitud || creandoSolicitud) return;

    try {
      setCreandoSolicitud(true);

      const datos = new FormData();
      datos.append("servicio_nombre", opcion.nombre);
      datos.append("tipo_servicio", opcion.categoria || "otro");
      datos.append(
        "notas",
        `${opcion.direccion || "Sin dirección"} · ${
          opcion.tiempo_min != null ? opcion.tiempo_min + " min" : "tiempo no verificado"
        }`
      );

      const respuesta = await fetch(`${API}/casos/${caso.caso_id}/solicitud`, {
        method: "POST",
        body: datos,
      });

      const resultado = await respuesta.json();

      if (resultado.error) {
        alert(resultado.mensaje);
        return;
      }

      setSolicitud(resultado.solicitud);
      await verCaso(caso.caso_id); // refresca la trazabilidad
      await cargarHistorial();
    } catch {
      alert("No fue posible registrar la solicitud.");
    } finally {
      setCreandoSolicitud(false);
    }
  };

  // ================================================
  // CHAT CONTEXTUAL
  // ================================================

  const enviarPregunta = async (e) => {
    e.preventDefault();

    if (!pregunta.trim() || enviandoChat || !caso) return;

    const preguntaActual = pregunta.trim();

    setMensajes((anteriores) => [
      ...anteriores,
      { tipo: "usuario", texto: preguntaActual },
    ]);
    setPregunta("");
    setEnviandoChat(true);

    try {
      const datos = new FormData();
      datos.append("pregunta", preguntaActual);

      const respuesta = await fetch(`${API}/casos/${caso.caso_id}/chat`, {
        method: "POST",
        body: datos,
      });

      if (!respuesta.ok) throw new Error();

      const resultado = await respuesta.json();

      setMensajes((anteriores) => [
        ...anteriores,
        {
          tipo: "ia",
          texto: resultado.respuesta || resultado.mensaje || "Sin respuesta del asistente.",
        },
      ]);
    } catch {
      setMensajes((anteriores) => [
        ...anteriores,
        { tipo: "ia", texto: "No fue posible obtener una respuesta en este momento." },
      ]);
    } finally {
      setEnviandoChat(false);
    }
  };

  const analisis = caso?.analisis || {};
  const completado = caso?.estado === "completado";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <span className="brand-icon">✦</span>
          <span className="brand">NEXUS VIAL</span>
        </div>

        <span className="system-status">
          <span className="status-dot"></span>
          Sistema activo
        </span>
      </header>

      <section className="hero">
        <div>
          <span className="hero-label">MOVILIDAD Y SERVICIOS URBANOS</span>

          <h1>
            Asistencia vial,
            <br />
            <span>resuelta con agentes de IA.</span>
          </h1>

          <p>
            Cuéntanos qué le pasó a tu vehículo, adjunta una foto e indica dónde
            estás. Los agentes analizan el caso, ubican tu origen y buscan los
            servicios más cercanos con ruta real.
          </p>
        </div>

        <div className="hero-number">
          <span>IA</span>
          <small>MULTIMODAL</small>
        </div>
      </section>

      <main className="workspace">
        {/* 01. NUEVO CASO */}

        <section className="incident-panel">
          <div className="section-heading">
            <div className="number">01</div>
            <div>
              <h2>Nuevo caso</h2>
              <p>Ubicación, descripción y evidencia</p>
            </div>
          </div>

          <form onSubmit={analizarCaso}>
            <div className="field">
              <label htmlFor="ubicacion">TU UBICACIÓN (ORIGEN)</label>
              <input
                id="ubicacion"
                type="text"
                value={ubicacion}
                onChange={(e) => setUbicacion(e.target.value)}
                placeholder="Ej. Carrera 7 con calle 72, Bogotá"
              />
            </div>

            <div className="field">
              <label htmlFor="descripcion">DESCRIPCIÓN DEL PROBLEMA</label>
              <textarea
                id="descripcion"
                rows="6"
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                placeholder="Describe qué le ocurrió al vehículo..."
              />
            </div>

            <div className="field">
              <label>EVIDENCIA VISUAL</label>

              <label className="upload-box">
                <span className="upload-icon">＋</span>

                {imagen ? (
                  <>
                    <strong>{imagen.name}</strong>
                    <small>Imagen seleccionada</small>
                  </>
                ) : (
                  <>
                    <strong>Seleccionar imagen</strong>
                    <small>JPG, PNG o WEBP</small>
                  </>
                )}

                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) => setImagen(e.target.files?.[0] || null)}
                  hidden
                />
              </label>
            </div>

            <button className="analyze-button" type="submit" disabled={cargando}>
              {cargando ? "Procesando caso..." : "Analizar con IA"}
              <span>→</span>
            </button>
          </form>
        </section>

        {/* 02. RESULTADO */}

        <section className="analysis-panel">
          <div className="section-heading">
            <div className="number purple">02</div>
            <div>
              <h2>Análisis y recomendación</h2>
              <p>Resultado de los agentes</p>
            </div>
          </div>

          {!caso && !cargando && !errorAnalisis && (
            <div className="empty-analysis">
              <div className="ai-orbit">
                <span>AI</span>
              </div>
              <h3>Esperando el caso</h3>
              <p>Completa los datos para iniciar el análisis.</p>
              <div className="analysis-tags">
                <span>VISIÓN</span>
                <span>UBICACIÓN</span>
                <span>RUTAS</span>
                <span>ACCIÓN</span>
              </div>
            </div>
          )}

          {cargando && (
            <div className="loading-analysis">
              <div className="loader"></div>
              <h3>Orquestando agentes con LangGraph</h3>
              <p>
                Analizando evidencia, ubicando el origen y consultando servicios
                cercanos...
              </p>
            </div>
          )}

          {errorAnalisis && !cargando && (
            <div className="analysis-error" role="alert">
              <strong>No se completó el análisis</strong>
              <p>{errorAnalisis}</p>
            </div>
          )}

          {caso && !cargando && (
            <>
              <div className="case-banner">
                <strong>{caso.codigo}</strong>
                <span>{caso.ubicacion_texto}</span>
                {caso.coordenadas?.direccion && (
                  <small>Resuelto como: {caso.coordenadas.direccion}</small>
                )}
              </div>

              {!completado && (
                <div className="estado-aviso" role="alert">
                  <strong>
                    {caso.estado === "requiere_informacion"
                      ? "Se necesita más información"
                      : "No se pudo completar el caso"}
                  </strong>
                  <p>{caso.mensaje}</p>
                </div>
              )}

              {/* DATOS ESTRUCTURADOS */}

              <div className="structured-analysis">
                <div className="structured-title">
                  <span>✦ ANÁLISIS ESTRUCTURADO</span>
                  <small>AGENTE ANALISTA</small>
                </div>

                <div className="structured-grid">
                  <div className="structured-card">
                    <span className="structured-label">NECESIDAD</span>
                    <strong>{analisis.tipo_necesidad}</strong>
                  </div>

                  <div className="structured-card">
                    <span className="structured-label">URGENCIA</span>
                    <strong className={`urgencia urgencia-${analisis.urgencia}`}>
                      {analisis.urgencia?.toUpperCase()}
                    </strong>
                  </div>

                  <div className="structured-card">
                    <span className="structured-label">SERVICIO REQUERIDO</span>
                    <strong>
                      {ETIQUETAS_CATEGORIA[analisis.categoria_servicio] ||
                        analisis.categoria_servicio}
                    </strong>
                  </div>

                  <div className="structured-card">
                    <span className="structured-label">INFORMACIÓN SUFICIENTE</span>
                    <strong>{analisis.informacion_suficiente ? "SÍ" : "NO"}</strong>
                  </div>

                  <div className="structured-card">
                    <span className="structured-label">OBSERVACIÓN</span>
                    <p>{analisis.observacion}</p>
                  </div>

                  <div className="structured-card">
                    <span className="structured-label">POSIBLE CAUSA</span>
                    <p>{analisis.posible_causa}</p>
                  </div>

                  <div className="structured-card">
                    <span className="structured-label">ACCIÓN RECOMENDADA</span>
                    <p>{analisis.accion_recomendada}</p>
                  </div>

                  <div className="structured-card">
                    <span className="structured-label">INCONSISTENCIAS</span>
                    <p>{analisis.inconsistencias}</p>
                  </div>
                </div>
              </div>

              {/* RECOMENDACIÓN Y OPCIONES */}

              {completado && caso.recomendacion?.servicio_sugerido && (
                <div className="result-box">
                  <div className="result-header">
                    <span>✦ RECOMENDACIÓN</span>
                    <span className="completed">AGENTE RECOMENDADOR</span>
                  </div>

                  <div className="equipment">
                    SUGERIDO: <strong>{caso.recomendacion.servicio_sugerido}</strong>
                  </div>

                  <div className="result-content">
                    <p>{caso.recomendacion.justificacion}</p>
                    {caso.recomendacion.advertencias && (
                      <p>
                        <strong>Ten en cuenta:</strong> {caso.recomendacion.advertencias}
                      </p>
                    )}
                  </div>

                  <div className="options-list">
                    {caso.opciones.map((op, i) => (
                      <div className="option-card" key={i}>
                        <div className="option-top">
                          <strong>{op.nombre}</strong>
                          <span className="badge-fuente">
                            {op.fuente === "datos_propios" ? "DATOS PROPIOS" : "GEOAPIFY"}
                          </span>
                        </div>

                        <small>{op.direccion || "Dirección no disponible"}</small>

                        <div className="option-meta">
                          <span>
                            {op.distancia_ruta_km != null
                              ? `${op.distancia_ruta_km} km por vía`
                              : `${op.distancia_directa_km} km en línea recta`}
                          </span>
                          <span>
                            {op.tiempo_min != null
                              ? `~${op.tiempo_min} min`
                              : "tiempo no verificado"}
                          </span>
                          {op.telefono && <span>☎ {op.telefono}</span>}
                          {op.servicio_24h && <span>24 h</span>}
                        </div>

                        {!solicitud && (
                          <button
                            type="button"
                            className="ticket-button"
                            onClick={() => registrarSolicitud(op)}
                            disabled={creandoSolicitud}
                          >
                            {creandoSolicitud
                              ? "Registrando..."
                              : "Solicitar asistencia con este servicio"}
                          </button>
                        )}
                      </div>
                    ))}
                  </div>

                  {solicitud && (
                    <div className="ticket-created">
                      <strong>✓ Solicitud registrada</strong>
                      <span>{solicitud.solicitud}</span>
                      <small>
                        Servicio: {solicitud.servicio_nombre}
                        {" · "}
                        Estado: {solicitud.estado}
                      </small>
                    </div>
                  )}
                </div>
              )}

              {/* CHAT CONTEXTUAL */}

              <div className="incident-chat">
                <div className="chat-heading">
                  <div>
                    <span className="chat-label">ASISTENTE DEL CASO</span>
                    <h3>Consulta este caso</h3>
                  </div>
                  <span className="chat-status">● IA</span>
                </div>

                <div className="chat-messages">
                  {mensajes.length === 0 && (
                    <div className="chat-intro">
                      Puedes preguntar por las opciones, las distancias, otros
                      servicios cercanos o los pasos a seguir en este caso.
                    </div>
                  )}

                  {mensajes.map((mensaje, index) => (
                    <div
                      key={index}
                      className={
                        mensaje.tipo === "usuario"
                          ? "message user-message"
                          : "message ai-message"
                      }
                    >
                      {mensaje.tipo === "ia" ? (
                        <ReactMarkdown>{mensaje.texto}</ReactMarkdown>
                      ) : (
                        mensaje.texto
                      )}
                    </div>
                  ))}

                  {enviandoChat && (
                    <div className="message ai-message">Consultando el contexto...</div>
                  )}
                </div>

                <form className="chat-form" onSubmit={enviarPregunta}>
                  <input
                    type="text"
                    value={pregunta}
                    onChange={(e) => setPregunta(e.target.value)}
                    placeholder="Pregunta algo sobre este caso..."
                    disabled={enviandoChat}
                  />
                  <button type="submit" disabled={enviandoChat || !pregunta.trim()}>
                    →
                  </button>
                </form>
              </div>

              {/* TRAZABILIDAD */}

              {caso.trazabilidad?.length > 0 && (
                <div className="agent-trace">
                  <div className="agent-trace-heading">
                    <span>✦ TRAZABILIDAD DEL CASO</span>
                    <small>{caso.trazabilidad.length} eventos</small>
                  </div>

                  <div className="agent-trace-steps">
                    {caso.trazabilidad.map((paso, index) => (
                      <div className="agent-trace-step" key={index}>
                        <span className="agent-trace-number">{index + 1}</span>
                        <span>
                          <strong>{paso.agente}</strong>
                          {paso.herramienta && ` · ${paso.herramienta}`}
                          <br />
                          <small>{paso.detalle}</small>
                        </span>
                      </div>
                    ))}
                  </div>

                  <p className="agent-trace-note">
                    Cada evento se guarda en la base de datos. La solicitud solo se
                    registra con aprobación del usuario.
                  </p>
                </div>
              )}
            </>
          )}
        </section>
      </main>

      {/* 03. HISTORIAL */}

      <section className="history-section">
        <div className="history-panel">
          <div className="history-top">
            <div className="section-heading">
              <div className="number history-number">03</div>
              <div>
                <h2>Historial de casos</h2>
                <p>Casos, resultados y solicitudes almacenados en SQLite</p>
              </div>
            </div>

            <div className="history-actions">
              <span className="history-count">{historial.length} registros</span>

              <button
                type="button"
                className="history-refresh"
                onClick={cargarHistorial}
                disabled={cargandoHistorial}
              >
                {cargandoHistorial ? "Actualizando..." : "↻ Actualizar"}
              </button>
            </div>
          </div>

          {errorHistorial && <p className="history-error">{errorHistorial}</p>}

          {!errorHistorial && !cargandoHistorial && historial.length === 0 && (
            <div className="history-empty">Aún no hay casos registrados.</div>
          )}

          {historial.length > 0 && (
            <div className="history-table-wrap">
              <table className="history-table">
                <thead>
                  <tr>
                    <th>CASO</th>
                    <th>UBICACIÓN</th>
                    <th>NECESIDAD</th>
                    <th>URGENCIA</th>
                    <th>ESTADO</th>
                    <th>SOLICITUD</th>
                    <th>FECHA</th>
                    <th></th>
                  </tr>
                </thead>

                <tbody>
                  {historial.map((item) => (
                    <tr key={item.caso_id}>
                      <td>
                        <strong className="history-id">{item.codigo}</strong>
                      </td>
                      <td className="history-description">{item.ubicacion_texto}</td>
                      <td>{item.necesidad}</td>
                      <td>
                        <span
                          className={`history-priority ${item.urgencia?.toLowerCase() || ""}`}
                        >
                          {item.urgencia || "—"}
                        </span>
                      </td>
                      <td>
                        <span className="history-state">{item.estado}</span>
                      </td>
                      <td>{item.solicitud || "—"}</td>
                      <td>{item.fecha_creacion}</td>
                      <td>
                        <button
                          type="button"
                          className="history-refresh"
                          onClick={() => verCaso(item.caso_id)}
                        >
                          Ver
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <footer>
        ASISTENCIA VIAL IA · FASTAPI + GEMINI + GEOAPIFY + REACT + SQLITE + LANGGRAPH
      </footer>
    </div>
  );
}

export default App;
