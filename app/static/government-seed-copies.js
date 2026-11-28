(() => {
  const form = document.querySelector("#seed-create-form");
  if (!form) return;

  const periodInput = document.querySelector("#seed-period");
  const countInput = document.querySelector("#seed-count");
  const createButton = document.querySelector("#seed-create-button");
  const status = document.querySelector("#seed-status");
  const listStatus = document.querySelector("#seed-batches-status");
  const list = document.querySelector("#seed-batches-list");

  const text = (element, value) => { element.textContent = value; };

  function suggestedPeriod(existing) {
    const now = new Date();
    const month = `${now.getMonth() + 1}`.padStart(2, "0");
    const base = `${now.getFullYear()}-${month}-demo-`;
    let suffix = 1;
    while (existing.has(`${base}${`${suffix}`.padStart(2, "0")}`)) suffix += 1;
    return `${base}${`${suffix}`.padStart(2, "0")}`;
  }

  function localizedDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat("es-MX", { dateStyle: "medium", timeStyle: "short" }).format(date);
  }

  async function loadBatches() {
    text(listStatus, "Cargando lotes…");
    listStatus.removeAttribute("data-state");
    list.replaceChildren();
    try {
      const response = await fetch("/api/planting/batches", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error(response.status === 401 ? "Inicia sesión en el panel gubernamental para ver los lotes." : "No se pudo consultar la lista de lotes.");
      const batches = await response.json();
      if (!periodInput.value) periodInput.value = suggestedPeriod(new Set(batches.map((batch) => batch.seed_period)));
      if (batches.length === 0) {
        text(listStatus, "Todavía no hay lotes sintéticos.");
        return;
      }
      text(listStatus, `${batches.length} ${batches.length === 1 ? "lote disponible" : "lotes disponibles"}.`);
      for (const batch of batches) {
        const row = document.createElement("li");
        row.className = "seed-batch-row";
        const detail = document.createElement("div");
        const heading = document.createElement("h3");
        text(heading, batch.seed_period);
        const meta = document.createElement("p");
        meta.className = "seed-batch-meta";
        text(meta, `${batch.total_copies} ${batch.total_copies === 1 ? "copia" : "copias"} · creado ${localizedDate(batch.updated_at)} · SHA-256 ${batch.manifest_hash.slice(-12)}`);
        detail.append(heading, meta);
        const download = document.createElement("a");
        download.className = "seed-download";
        download.href = `/api/planting/batches/${encodeURIComponent(batch.seed_period)}/download`;
        download.textContent = "Descargar ZIP";
        download.setAttribute("aria-label", `Descargar copias del lote ${batch.seed_period}`);
        row.append(detail, download);
        list.append(row);
      }
    } catch (error) {
      text(listStatus, error instanceof Error ? error.message : "No se pudo consultar la lista de lotes.");
      listStatus.dataset.state = "error";
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    createButton.disabled = true;
    text(createButton, "Generando…");
    text(status, "Creando bases SQLite sintéticas…");
    status.removeAttribute("data-state");
    try {
      const response = await fetch("/api/planting/batches", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ seed_period: periodInput.value.trim(), total_copies: Number(countInput.value) }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || "No se pudo crear el lote.");
      text(status, `Lote ${payload.seed_period} creado con ${payload.total_copies} copias sintéticas.`);
      status.dataset.state = "success";
      periodInput.value = "";
      await loadBatches();
      periodInput.value = suggestedPeriod(new Set(Array.from(list.querySelectorAll("h3"), (heading) => heading.textContent)));
    } catch (error) {
      text(status, error instanceof Error ? error.message : "No se pudo crear el lote.");
      status.dataset.state = "error";
    } finally {
      createButton.disabled = false;
      text(createButton, "Generar copias");
    }
  });

  document.querySelector("#seed-refresh").addEventListener("click", loadBatches);
  loadBatches();
})();
