(() => {
  const byId = (id) => document.getElementById(id);
  const status = byId("reports-status");
  const reportDialog = byId("report-detail-dialog");
  let activeReport = null;
  const typeNames = { call: "Llamada", sms_analysis: "Análisis SMS", citizen_report: "Reporte ciudadano" };
  const channelNames = { llamada: "Voz", sms: "SMS" };
  const statusNames = {
    sin_alerta: "Sin alerta", sin_verificar: "Sin verificar", indicio: "Indicio",
    campana_corroborada: "Campaña corroborada", corroborada: "Corroborada",
    sospechoso: "Sospechoso", active: "Activa", ended: "Terminada", cancelled: "Cancelada",
  };

  const number = (value) => new Intl.NumberFormat("es-MX").format(value || 0);
  const safeText = (value, fallback = "—") => typeof value === "string" && value.trim() ? value : fallback;

  function setStatus(message, error = false) {
    status.textContent = message;
    status.dataset.state = error ? "error" : "ok";
  }

  function renderTrend(timeline) {
    const host = byId("trend-chart");
    host.replaceChildren();
    if (!timeline.length) {
      host.textContent = "Todavía no hay actividad guardada en este periodo.";
      host.classList.add("table-empty");
      return;
    }
    host.classList.remove("table-empty");
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 680 220");
    svg.setAttribute("role", "presentation");
    const pad = { left: 34, right: 12, top: 12, bottom: 28 };
    const width = 680 - pad.left - pad.right;
    const height = 220 - pad.top - pad.bottom;
    const maxValue = Math.max(1, ...timeline.map((d) => d.total));
    [0, 0.5, 1].forEach((fraction) => {
      const y = pad.top + height * (1 - fraction);
      const line = document.createElementNS(ns, "line");
      line.setAttribute("x1", pad.left); line.setAttribute("x2", 680 - pad.right);
      line.setAttribute("y1", y); line.setAttribute("y2", y); line.setAttribute("class", "chart-gridline"); svg.appendChild(line);
      const label = document.createElementNS(ns, "text");
      label.setAttribute("x", pad.left - 9); label.setAttribute("y", y + 4); label.setAttribute("text-anchor", "end");
      label.setAttribute("class", "chart-axis-label"); label.textContent = String(Math.round(maxValue * fraction)); svg.appendChild(label);
    });
    const points = timeline.map((item, index) => {
      const x = pad.left + (timeline.length === 1 ? width / 2 : width * index / (timeline.length - 1));
      const y = pad.top + height * (1 - item.total / maxValue);
      return { x, y, item };
    });
    const area = document.createElementNS(ns, "path");
    area.setAttribute("d", `M ${points[0].x} ${pad.top + height} ${points.map((p) => `L ${p.x} ${p.y}`).join(" ")} L ${points.at(-1).x} ${pad.top + height} Z`);
    area.setAttribute("class", "chart-area"); svg.appendChild(area);
    const path = document.createElementNS(ns, "path");
    path.setAttribute("d", points.map((p, i) => `${i ? "L" : "M"} ${p.x} ${p.y}`).join(" ")); path.setAttribute("class", "chart-line"); svg.appendChild(path);
    points.forEach((point, index) => {
      const dot = document.createElementNS(ns, "circle"); dot.setAttribute("cx", point.x); dot.setAttribute("cy", point.y); dot.setAttribute("r", 4); dot.setAttribute("class", "chart-point");
      const title = document.createElementNS(ns, "title"); title.textContent = `${point.item.day}: ${point.item.total} registros`;
      dot.appendChild(title); svg.appendChild(dot);
      if (index === 0 || index === points.length - 1 || (timeline.length > 7 && index % Math.ceil(timeline.length / 5) === 0)) {
        const label = document.createElementNS(ns, "text"); label.setAttribute("x", point.x); label.setAttribute("y", 214); label.setAttribute("text-anchor", index === 0 ? "start" : index === points.length - 1 ? "end" : "middle"); label.setAttribute("class", "chart-axis-label");
        label.textContent = new Date(`${point.item.day}T12:00:00`).toLocaleDateString("es-MX", { day: "2-digit", month: "short" }); svg.appendChild(label);
      }
    });
    host.appendChild(svg);
  }

  function renderTypes(byType, total) {
    const host = byId("type-chart");
    host.replaceChildren();
    [["call", "Llamadas"], ["sms_analysis", "Análisis SMS"], ["citizen_report", "Ciudadanía"]].forEach(([key, label]) => {
      const count = byType[key] || 0;
      const row = document.createElement("div"); row.className = "type-row";
      const name = document.createElement("span"); name.textContent = label;
      const track = document.createElement("span"); track.className = "type-track";
      const bar = document.createElement("span"); bar.className = "type-bar"; bar.style.display = "block"; bar.style.transform = `scaleX(${total ? count / total : 0})`; track.appendChild(bar);
      const value = document.createElement("span"); value.className = "type-count"; value.textContent = number(count);
      row.append(name, track, value); host.appendChild(row);
    });
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleString("es-MX", { dateStyle: "medium", timeStyle: "short" });
  }

  function renderRecent(rows) {
    const body = byId("reports-list"); body.replaceChildren();
    byId("recent-count").textContent = `${number(rows.length)} ${rows.length === 1 ? "registro" : "registros"}`;
    if (!rows.length) {
      const tr = document.createElement("tr"); const td = document.createElement("td"); td.colSpan = 7; td.className = "table-empty"; td.textContent = "Todavía no hay reportes guardados. Analiza un SMS, envía un reporte ciudadano o termina una llamada simulada."; tr.appendChild(td); body.appendChild(tr); return;
    }
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      const date = document.createElement("td"); const time = document.createElement("time"); time.dateTime = row.created_at; time.textContent = formatDate(row.created_at); date.appendChild(time);
      const type = document.createElement("td"); type.className = "record-type";
      const scenarioLabel = row.report_type === "call" && row.details?.scenario_id ? ` · ${row.details.scenario_id}` : "";
      type.textContent = `${typeNames[row.report_type] || "Reporte"}${scenarioLabel}`;
      const result = document.createElement("td"); const tag = document.createElement("span"); tag.className = "status-tag"; tag.dataset.status = row.status; tag.textContent = statusNames[row.status] || row.status || "Sin estado"; result.appendChild(tag);
      const municipality = document.createElement("td"); municipality.textContent = safeText(row.municipality, "No especificado");
      const confidence = document.createElement("td"); confidence.textContent = `${Math.round((row.confidence || 0) * 100)}%`;
      const origin = document.createElement("td"); origin.className = "record-origin";
      const draft = row.details?.draft_status === "borrador_exportado" ? " · Borrador exportado" : "";
      origin.textContent = `${row.synthetic ? "Simulación local" : safeText(channelNames[row.channel], "Ciudadanía")}${draft}`;
      const detail = document.createElement("td");
      const view = document.createElement("button"); view.type = "button"; view.className = "report-view-button";
      view.dataset.reportId = row.report_id; view.textContent = "Consultar"; view.setAttribute("aria-label", `Consultar reporte ${row.report_id}`);
      detail.appendChild(view);
      tr.append(date, type, result, municipality, confidence, origin, detail); body.appendChild(tr);
    });
  }

  async function showReport(reportId) {
    setStatus("Consultando reporte guardado…");
    try {
      const response = await fetch(`/api/gobierno/reportes/${encodeURIComponent(reportId)}`, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`No se pudo consultar el reporte (${response.status}).`);
      activeReport = await response.json();
      byId("report-detail-content").textContent = JSON.stringify(activeReport, null, 2);
      reportDialog.showModal();
      setStatus("Reporte consultado desde el historial local.");
    } catch (error) {
      setStatus(error.message, true);
    }
  }

  byId("reports-list").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-report-id]");
    if (button) showReport(button.dataset.reportId);
  });
  byId("report-detail-close").addEventListener("click", () => reportDialog.close());
  byId("report-detail-download").addEventListener("click", () => {
    if (!activeReport) return;
    const id = activeReport.report?.report_id || "reporte";
    const url = URL.createObjectURL(new Blob([JSON.stringify(activeReport, null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `reporte-demo-${id}.json`; link.click();
    URL.revokeObjectURL(url);
  });

  async function load() {
    setStatus("Actualizando métricas e historial…");
    const days = byId("period-select").value;
    try {
      const response = await fetch(`/api/gobierno/reportes-resumen?days=${encodeURIComponent(days)}`, { credentials: "same-origin" });
      if (!response.ok) throw new Error(`No se pudo cargar el historial (${response.status}).`);
      const data = await response.json();
      byId("metric-total").textContent = number(data.total);
      byId("metric-suspicious").textContent = `${number(data.suspicious)} · ${Math.round(data.suspicious_rate * 100)}%`;
      byId("metric-campaigns").textContent = number(data.campaigns);
      byId("metric-drafts").textContent = number(data.drafts_exported);
      byId("trend-total").textContent = number(data.total);
      byId("risk-summary").textContent = data.suspicious ? `${number(data.suspicious)} registros con señales de riesgo` : "Sin registros con señales en el periodo";
      renderTrend(data.timeline || []);
      renderTypes(data.by_type || {}, data.total || 0);
      renderRecent(data.recent || []);
      setStatus(`Historial local actualizado · últimos ${data.days} días.`);
    } catch (error) {
      setStatus(error.message, true);
      byId("reports-list").innerHTML = '<tr><td colspan="7" class="table-empty">No se pudo cargar el historial. Revisa la conexión y vuelve a intentarlo.</td></tr>';
    }
  }

  byId("period-select").addEventListener("change", load);
  load();
})();
