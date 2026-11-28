(function () {
  "use strict";

  function clearNode(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function createBadge(text, extraClass) {
    const span = document.createElement("span");
    span.className = "badge" + (extraClass ? " " + extraClass : "");
    span.textContent = text;
    return span;
  }

  function renderDashboard(data) {
    const summary = data.summary || {};
    document.getElementById("kpi-total-events").textContent = String(summary.total_events ?? 0);
    document.getElementById("kpi-attributed").textContent = String(summary.attributed_events ?? 0);
    document.getElementById("kpi-campaigns").textContent = String(summary.active_campaigns ?? 0);
    document.getElementById("kpi-copies").textContent = String(summary.seeded_copies ?? 0);
    document.getElementById("kpi-lead-time").textContent =
      summary.best_lead_time_hours !== null && summary.best_lead_time_hours !== undefined
        ? summary.best_lead_time_hours + " h"
        : "—";
    document.getElementById("dashboard-manifest-hash").textContent = summary.seed_manifest_hash || "";

    const tbody = document.getElementById("attributions-tbody");
    const emptyBox = document.getElementById("attributions-empty");
    const table = document.getElementById("attributions-table");
    clearNode(tbody);

    const rows = data.attributions || [];
    if (rows.length === 0) {
      table.style.display = "none";
      emptyBox.style.display = "block";
      emptyBox.textContent = data.empty_state || "No hay eventos sintéticos disponibles.";
    } else {
      table.style.display = "table";
      emptyBox.style.display = "none";

      rows.forEach(function (row) {
        const tr = document.createElement("tr");

        const tdEvent = document.createElement("td");
        const strongId = document.createElement("strong");
        strongId.textContent = row.event_id;
        const meta = document.createElement("div");
        meta.className = "muted";
        meta.textContent = row.channel + " · " + row.occurred_at;
        tdEvent.appendChild(strongId);
        tdEvent.appendChild(meta);

        const tdTrap = document.createElement("td");
        tdTrap.className = "mono";
        tdTrap.textContent = row.trap_display || "Sin número trampa";

        const tdCopy = document.createElement("td");
        if (row.attribution_status === "atribuido") {
          const copyCode = document.createElement("div");
          copyCode.className = "mono";
          copyCode.textContent = row.copy_id || "";
          const prov = document.createElement("div");
          prov.className = "muted";
          prov.textContent = row.provider || "";
          tdCopy.appendChild(copyCode);
          tdCopy.appendChild(prov);
        } else {
          tdCopy.appendChild(createBadge("no_atribuido", ""));
        }

        const tdInd = document.createElement("td");
        const inds = row.masked_indicators || [];
        tdInd.textContent = inds.length > 0 ? inds.join(", ") : "Sin indicadores";

        const tdStatus = document.createElement("td");
        tdStatus.appendChild(createBadge(row.status, "badge-" + row.status));
        const confDiv = document.createElement("div");
        confDiv.className = "muted";
        confDiv.textContent = "confianza: " + row.confidence;
        tdStatus.appendChild(confDiv);

        const tdExp = document.createElement("td");
        tdExp.textContent = row.explanation;

        tr.appendChild(tdEvent);
        tr.appendChild(tdTrap);
        tr.appendChild(tdCopy);
        tr.appendChild(tdInd);
        tr.appendChild(tdStatus);
        tr.appendChild(tdExp);
        tbody.appendChild(tr);
      });
    }

    const campaignsEl = document.getElementById("campaigns-list");
    clearNode(campaignsEl);
    const campaigns = data.campaigns || [];
    if (campaigns.length === 0) {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "Sin campañas para el filtro seleccionado.";
      campaignsEl.appendChild(p);
    } else {
      campaigns.forEach(function (camp) {
        const box = document.createElement("div");
        box.style.border = "1px solid #d8e0ea";
        box.style.borderRadius = "8px";
        box.style.padding = "10px 12px";
        box.style.marginBottom = "10px";

        const header = document.createElement("div");
        header.style.display = "flex";
        header.style.justifyContent = "space-between";
        header.style.gap = "8px";
        const title = document.createElement("strong");
        title.textContent = camp.title;
        header.appendChild(title);
        header.appendChild(createBadge(camp.status + " · " + camp.confidence, "badge-" + camp.status));

        const info = document.createElement("div");
        info.className = "muted";
        info.style.marginTop = "4px";
        const leadText = camp.lead_time_hours !== null && camp.lead_time_hours !== undefined
          ? " · Ventaja: " + camp.lead_time_hours + " h"
          : "";
        info.textContent =
          "Marca: " + camp.brand +
          " · Trampas alcanzadas: " + camp.traps_reached_count +
          " · Eventos: " + camp.event_count +
          leadText;

        const sim = document.createElement("div");
        sim.className = "muted";
        sim.style.fontSize = "0.78rem";
        sim.style.marginTop = "4px";
        sim.textContent = camp.simulated_third_party_notice;

        box.appendChild(header);
        box.appendChild(info);
        box.appendChild(sim);
        campaignsEl.appendChild(box);
      });
    }
  }

  function projectGeoJsonToSvg(geojson) {
    const svg = document.getElementById("qro-map-svg");
    const tooltip = document.getElementById("map-tooltip");
    clearNode(svg);

    const features = (geojson && geojson.features) || [];
    if (features.length === 0) return;

    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    features.forEach(function (feat) {
      const coords = feat.geometry && feat.geometry.coordinates ? feat.geometry.coordinates : [];
      const rings = feat.geometry.type === "MultiPolygon" ? coords.flat() : coords;
      rings.forEach(function (ring) {
        ring.forEach(function (pt) {
          if (pt[0] < minX) minX = pt[0];
          if (pt[0] > maxX) maxX = pt[0];
          if (pt[1] < minY) minY = pt[1];
          if (pt[1] > maxY) maxY = pt[1];
        });
      });
    });

    const width = 640, height = 520, pad = 24;
    const spanX = (maxX - minX) || 1;
    const spanY = (maxY - minY) || 1;
    const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
    const offsetX = (width - spanX * scale) / 2;
    const offsetY = (height - spanY * scale) / 2;

    function projectPoint(pt) {
      const x = offsetX + (pt[0] - minX) * scale;
      const y = height - (offsetY + (pt[1] - minY) * scale);
      return [x.toFixed(1), y.toFixed(1)];
    }

    features.forEach(function (feat) {
      const props = feat.properties || {};
      const coords = feat.geometry.type === "MultiPolygon" ? feat.geometry.coordinates.flat() : feat.geometry.coordinates;
      let pathD = "";
      coords.forEach(function (ring) {
        ring.forEach(function (pt, idx) {
          const p = projectPoint(pt);
          pathD += (idx === 0 ? "M" : "L") + p[0] + " " + p[1] + " ";
        });
        pathD += "Z ";
      });

      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", pathD.trim());
      path.setAttribute("stroke", "#334155");
      path.setAttribute("stroke-width", "1.2");

      let fill = "#e2e8f0";
      if (props.suppressed) {
        fill = "#fde68a";
      } else if (typeof props.count === "number" && props.count >= 5) {
        fill = props.count >= 10 ? "#144d8a" : "#4b86c6";
      }
      path.setAttribute("fill", fill);
      path.style.cursor = "pointer";

      path.addEventListener("mouseenter", function () {
        path.setAttribute("stroke-width", "2.4");
        tooltip.textContent = props.municipality_name + " (" + props.municipality_code + "): " + props.display_label;
      });
      path.addEventListener("mouseleave", function () {
        path.setAttribute("stroke-width", "1.2");
      });

      svg.appendChild(path);
    });
  }

  function renderMap(mapData) {
    document.getElementById("map-threshold").textContent = String(mapData.threshold ?? 5);
    document.getElementById("map-state-total").textContent = String(mapData.state_total ?? 0);
    document.getElementById("map-suppressed-count").textContent = String(mapData.suppressed_municipalities_count ?? 0);
    document.getElementById("map-rate-limited").textContent = String(mapData.excluded_rate_limited_count ?? 0);

    projectGeoJsonToSvg(mapData.geojson);

    const tbody = document.getElementById("map-municipalities-tbody");
    clearNode(tbody);
    (mapData.municipalities || []).forEach(function (m) {
      const tr = document.createElement("tr");
      const tdCode = document.createElement("td");
      tdCode.className = "mono";
      tdCode.textContent = m.municipality_code;

      const tdName = document.createElement("td");
      tdName.textContent = m.municipality_name;

      const tdStatus = document.createElement("td");
      const cls = m.suppressed ? "badge-indicio" : (m.count && m.count >= 5 ? "badge-corroborado" : "");
      tdStatus.appendChild(createBadge(m.display_label, cls));

      tr.appendChild(tdCode);
      tr.appendChild(tdName);
      tr.appendChild(tdStatus);
      tbody.appendChild(tr);
    });
  }

  async function fetchDashboard() {
    const form = document.getElementById("dashboard-filters");
    const params = new URLSearchParams();
    ["channel", "status", "confidence"].forEach(function (field) {
      const val = form.elements[field].value;
      if (val) params.set(field, val);
    });
    const res = await fetch("/api/dashboard?" + params.toString());
    const data = await res.json();
    renderDashboard(data);
  }

  async function fetchMap() {
    const res = await fetch("/api/map");
    const mapData = await res.json();
    renderMap(mapData);
  }

  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("dashboard-filters");
    const clearBtn = document.getElementById("btn-clear-filters");

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      fetchDashboard();
    });

    clearBtn.addEventListener("click", function () {
      form.reset();
      fetchDashboard();
    });

    fetchDashboard();
    fetchMap();
  });
})();
