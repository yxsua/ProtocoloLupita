(() => {
  const byId = (id) => document.getElementById(id);
  const timeline = byId("call-timeline");
  const statusLabel = byId("call-state");
  const caption = byId("call-caption");
  const connection = byId("connection-status");
  const reportButton = byId("report-button");
  const seen = new Set();
  let latestCallId = "";

  const intentNames = {
    asustarse: "Se mostró preocupado",
    pedir_repeticion: "Pidió que repitieran",
    preguntar_cuenta_deposito: "Preguntó por una cuenta",
    repetir_digitos: "Repitió cifras",
    dar_largas: "Ganó tiempo",
    despedirse: "Terminó la llamada",
  };
  const indicatorNames = {
    clabe: "Cuenta bancaria",
    card: "Tarjeta",
    origin_phone: "Número de origen",
    contact_phone: "Teléfono mencionado",
    url: "Enlace",
    requested_data: "Dato solicitado",
    brand: "Institución mencionada",
  };

  function localTime(value) {
    if (!value) return "Ahora";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Ahora" : date.toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" });
  }

  function setConnection(message, error = false) {
    connection.textContent = message;
    connection.dataset.state = error ? "error" : "ok";
  }

  function setCallState(label, state, note) {
    statusLabel.textContent = label;
    statusLabel.className = `state-pill ${state}`;
    if (note) caption.textContent = note;
  }

  function clearEmpty() {
    const empty = timeline.querySelector(".timeline-empty");
    if (empty) empty.remove();
  }

  function addTimelineItem({ time, label, text, reply, provisional = false }) {
    clearEmpty();
    const item = document.createElement("li");
    item.className = "timeline-item";
    const top = document.createElement("div");
    top.className = "timeline-top";
    const speaker = document.createElement("span");
    speaker.textContent = label;
    const timeText = document.createElement("time");
    timeText.textContent = localTime(time);
    top.append(speaker, timeText);
    item.appendChild(top);
    if (text) {
      const transcript = document.createElement("p");
      transcript.textContent = text;
      if (provisional) transcript.className = "provisional";
      item.appendChild(transcript);
    }
    if (reply) {
      const response = document.createElement("p");
      response.className = "agent-reply";
      response.textContent = `Doña Lupita: ${reply}`;
      item.appendChild(response);
    }
    timeline.appendChild(item);
    timeline.scrollTop = timeline.scrollHeight;
  }

  function updateAttribution(attribution, agent) {
    if (!attribution) return;
    byId("trace-agent").textContent = agent || "Doña Lupita";
    byId("trace-copy").textContent = attribution.copy_id || attribution.status || "No atribuida";
    const source = attribution.source_dataset || attribution.provider || "Fuente no disponible";
    const period = attribution.seed_period ? ` · ${attribution.seed_period}` : "";
    byId("trace-source").textContent = `${source}${period}`;
  }

  function updateIndicators(indicators) {
    const list = byId("indicator-list");
    list.replaceChildren();
    if (!Array.isArray(indicators) || indicators.length === 0) {
      const empty = document.createElement("li");
      empty.textContent = "Aún no hay señales.";
      list.appendChild(empty);
      return;
    }
    for (const indicator of indicators) {
      const item = document.createElement("li");
      const name = indicatorNames[indicator.type] || "Señal";
      const value = indicator.value_masked || "Valor oculto";
      const validity = indicator.valid === true ? " · validación correcta" : indicator.valid === false ? " · requiere revisión" : "";
      item.textContent = `${name}: ${value}${validity}`;
      list.appendChild(item);
    }
  }

  function handleEvent(event) {
    if (!event || seen.has(event.id)) return;
    seen.add(event.id);
    if (event.source_mode !== "telephony" && !String(event.kind).startsWith("call.")) return;

    if (event.kind === "call.started") {
      latestCallId = event.call_id || "";
      setCallState("En llamada", "active", "La sesión de llamada simulada está en curso.");
      byId("trace-caller").textContent = event.caller_masked || "No disponible";
      byId("trace-number").textContent = event.called_number_masked || "Número de prueba";
      byId("caller-note").textContent = "Identificador del llamante no verificado.";
      updateAttribution(event.attribution, event.agent);
      updateIndicators([]);
      reportButton.disabled = true;
      addTimelineItem({
        time: event.occurred_at,
        label: "Llamada entrante contestada",
        text: "La trampa ficticia quedó asociada a una copia sembrada.",
        reply: event.agent_response || "Doña Lupita respondió la llamada.",
      });
    } else if (event.kind === "call.partial") {
      addTimelineItem({ time: event.occurred_at, label: "Voz reconocida (provisional)", text: event.transcript || "", provisional: true });
    } else if (event.kind === "call.turn") {
      latestCallId = event.call_id || latestCallId;
      setCallState("En llamada", "active", event.intent ? (intentNames[event.intent] || "Se procesó un turno") : "Se procesó un turno de voz.");
      updateAttribution(event.attribution, "Doña Lupita");
      updateIndicators(event.indicators);
      addTimelineItem({
        time: event.occurred_at,
        label: event.scenario_id
          ? `${event.scenario_id} · Persona que llama`
          : event.intent ? (intentNames[event.intent] || "Turno reconocido") : "Turno reconocido",
        text: event.transcript || "",
        reply: event.agent_response || "",
      });
    } else if (event.kind === "call.ended") {
      latestCallId = event.call_id || latestCallId;
      setCallState("Llamada terminada", "ended", `Duración: ${event.duration_seconds || 0} s · resultado de demostración.`);
      updateAttribution(event.attribution, "Doña Lupita");
      updateIndicators(event.indicators);
      reportButton.disabled = false;
      addTimelineItem({ time: event.occurred_at, label: "Llamada finalizada", text: "El borrador puede prepararse para revisión." });
    } else if (event.kind === "call.capacity_rejected") {
      addTimelineItem({ time: event.occurred_at, label: "Sesión ocupada", text: "Solo se permite una simulación activa a la vez." });
    }
  }

  async function loadSnapshot() {
    const response = await fetch("/api/gobierno/snapshot", { credentials: "same-origin" });
    if (!response.ok) throw new Error(`No se pudo cargar el panel (${response.status}).`);
    const data = await response.json();
    for (const event of data.events || []) handleEvent(event);
    if (data.active_call) setCallState("En llamada", "active", "Hay una llamada activa.");
    setConnection("Conectado · esperando eventos de llamada.");
    return data.last_event_id || 0;
  }

  async function prepareReport() {
    if (!latestCallId) return;
    reportButton.disabled = true;
    reportButton.textContent = "Preparando…";
    try {
      const response = await fetch(`/api/gobierno/reportes/${encodeURIComponent(latestCallId)}/borrador`, {
        method: "POST", credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Todavía no hay un resultado para preparar.");
      const report = await response.json();
      const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `borrador-demo-${latestCallId}.json`;
      link.click();
      URL.revokeObjectURL(url);
      byId("report-note").textContent = "Borrador descargado. No se envió a ninguna autoridad.";
    } catch (error) {
      byId("report-note").textContent = error.message;
    } finally {
      reportButton.disabled = false;
      reportButton.textContent = "Preparar borrador";
    }
  }

  reportButton.addEventListener("click", prepareReport);

  loadSnapshot().then((lastId) => {
    const source = new EventSource(`/api/gobierno/eventos?after=${lastId}`);
    source.addEventListener("update", (message) => {
      try {
        handleEvent(JSON.parse(message.data));
        setConnection("Conectado · resultados actualizados en vivo.");
      } catch {
        setConnection("Llegó un evento que no se pudo mostrar.", true);
      }
    });
    source.onopen = () => setConnection("Conectado · resultados actualizados en vivo.");
    source.onerror = () => setConnection("Reconectando con el servidor…", true);
  }).catch((error) => setConnection(error.message, true));
})();
