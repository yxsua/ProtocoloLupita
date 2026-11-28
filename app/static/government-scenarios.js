(() => {
  const byId = (id) => document.getElementById(id);
  const select = byId("scenario-select");
  const runButton = byId("scenario-run");
  const status = byId("scenario-status");
  const resultBox = byId("scenario-result");
  const timeline = byId("scenario-timeline");
  const seen = new Set();
  let running = false;

  function addActivity(event) {
    if (!event || seen.has(event.id)) return;
    seen.add(event.id);
    if (event.source_mode !== "scenario") return;
    if (!event.kind.startsWith("scenario.")) return;
    const empty = timeline.querySelector(".timeline-empty");
    if (empty) empty.remove();
    const item = document.createElement("li");
    item.className = "timeline-item";
    const heading = document.createElement("div");
    heading.className = "timeline-top";
    const title = document.createElement("span");
    title.textContent = `${event.scenario_id || "Escenario"} · ${event.kind.replace("scenario.", "")}`;
    const time = document.createElement("time");
    time.textContent = event.occurred_at ? new Date(event.occurred_at).toLocaleTimeString("es-MX", { hour: "2-digit", minute: "2-digit" }) : "Ahora";
    heading.append(title, time);
    item.appendChild(heading);
    if (event.transcript) {
      const text = document.createElement("p");
      text.textContent = event.transcript;
      item.appendChild(text);
    }
    if (event.agent_response) {
      const response = document.createElement("p");
      response.className = "agent-reply";
      response.textContent = `Doña Lupita: ${event.agent_response}`;
      item.appendChild(response);
    }
    if (event.passed !== undefined) {
      const outcome = document.createElement("p");
      outcome.textContent = event.passed ? "Resultado: escenario aprobado." : "Resultado: revisar el escenario.";
      item.appendChild(outcome);
    }
    timeline.appendChild(item);
    timeline.scrollTop = timeline.scrollHeight;
  }

  function renderResult(data) {
    resultBox.className = "scenario-result";
    resultBox.replaceChildren();
    const heading = document.createElement("h3");
    heading.textContent = data.passed ? "Escenario aprobado" : "Escenario por revisar";
    resultBox.appendChild(heading);
    const details = document.createElement("dl");
    const rows = [
      ["Escenario", data.scenario_id],
      ["Modo", "Simulación controlada"],
      ["Duración", `${data.duration_ms} ms`],
      ["Intención final", data.voice?.ultima_intencion || "Sin intención"],
      ["Señal bancaria", data.voice?.clabe_detectada ? "Detectada" : "No detectada"],
      ["Validación", data.voice?.digito_verificador_ok === true ? "Correcta" : data.voice?.digito_verificador_ok === false ? "Requiere revisión" : "No aplica"],
      ["Campaña", data.intelligence?.campaign_id || "Sin campaña"],
    ];
    for (const [label, value] of rows) {
      const term = document.createElement("dt");
      term.textContent = label;
      const description = document.createElement("dd");
      description.textContent = value ?? "—";
      details.append(term, description);
    }
    resultBox.appendChild(details);
  }

  async function initialize() {
    const response = await fetch("/api/gobierno/snapshot", { credentials: "same-origin" });
    if (!response.ok) throw new Error("No se pudo cargar la lista de escenarios.");
    const data = await response.json();
    select.replaceChildren();
    for (const scenario of data.scenarios || []) {
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = `${scenario.id} · ${scenario.label}`;
      select.appendChild(option);
    }
    runButton.disabled = select.options.length === 0;
    status.textContent = runButton.disabled ? "No hay escenarios de llamada disponibles." : "Lista lista. Ejecuta un escenario cuando quieras.";
    for (const event of data.events || []) addActivity(event);
    const source = new EventSource(`/api/gobierno/eventos?after=${data.last_event_id || 0}`);
    source.addEventListener("update", (message) => {
      try { addActivity(JSON.parse(message.data)); } catch { /* ignore malformed updates */ }
    });
  }

  runButton.addEventListener("click", async () => {
    if (running || !select.value) return;
    running = true;
    runButton.disabled = true;
    runButton.textContent = "Ejecutando…";
    status.textContent = "El agente está procesando el escenario.";
    try {
      const response = await fetch(`/api/gobierno/escenarios/${encodeURIComponent(select.value)}/ejecutar`, {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "No se pudo ejecutar el escenario.");
      renderResult(data);
      status.textContent = data.passed ? "Prueba completada: resultado esperado." : "Prueba completada: revisar el resultado.";
    } catch (error) {
      status.textContent = error.message;
    } finally {
      running = false;
      runButton.disabled = select.options.length === 0;
      runButton.textContent = "Ejecutar escenario";
    }
  });

  initialize().catch((error) => { status.textContent = error.message; });
})();
