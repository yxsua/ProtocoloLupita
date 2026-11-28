async function showHealth() {
  const target = document.querySelector("#health");
  try {
    const response = await fetch("/api/health");
    const result = await response.json();
    target.textContent = `${result.status} · almacenamiento ${result.storage}`;
  } catch {
    target.textContent = "Sin conexión con la API";
  }
}

showHealth();

async function loadScenarios() {
  const list = document.querySelector("#scenario-list");
  const status = document.querySelector("#scenario-status");
  try {
    const [scenarioResponse, resultsResponse] = await Promise.all([
      fetch("/api/scenarios"),
      fetch("/api/scenarios/results"),
    ]);
    const scenarios = await scenarioResponse.json();
    const results = await resultsResponse.json();
    const latest = new Map(results.map((result) => [result.scenario_id, result]));
    list.replaceChildren();
    for (const scenario of scenarios) {
      const item = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = `${scenario.id} · ${scenario.channel}`;
      const state = document.createElement("span");
      state.className = "scenario-state";
      const result = latest.get(scenario.id);
      state.textContent = result ? (result.passed ? "Aprobado" : (result.actual?.error ? "Sin ejecutor" : "Falló")) : "Pendiente";
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "Ejecutar";
      button.addEventListener("click", () => runScenario(scenario.id, button, state));
      item.append(label, state, button);
      list.append(item);
    }
    status.textContent = scenarios.length ? `${scenarios.length} escenarios en el catálogo` : "Aún no hay escenarios JSON en data/scenarios";
  } catch {
    status.textContent = "No se pudo cargar el catálogo de escenarios";
  }
}

async function runScenario(id, button, state) {
  button.disabled = true;
  state.textContent = "Ejecutando…";
  try {
    const response = await fetch(`/api/scenarios/${encodeURIComponent(id)}/run`, { method: "POST" });
    if (!response.ok) throw new Error("No se pudo ejecutar el escenario");
    const result = await response.json();
    state.textContent = result.passed ? "Aprobado" : (result.actual?.error ? "Sin ejecutor" : "Falló");
  } catch {
    state.textContent = "Error";
  } finally {
    button.disabled = false;
  }
}

document.querySelector("#run-all").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  document.querySelector("#scenario-status").textContent = "Ejecutando escenarios…";
  try {
    await fetch("/api/scenarios/run-all", { method: "POST" });
    await loadScenarios();
  } finally {
    button.disabled = false;
  }
});

loadScenarios();
