(function () {
  "use strict";

  const labels = {
    call: "Llamada",
    sms: "Mensaje de texto",
    portal: "Reporte de otra persona",
    indicio: "En revisión",
    corroborado: "Coincide con otras señales",
    sin_verificar: "Aún no se puede verificar",
  };

  function make(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function describeAlert(alert) {
    const brand = String(alert.brand || "").toLowerCase();
    if (brand.includes("sat")) return "Mensaje que podría hacerse pasar por el SAT";
    if (brand.includes("cobro de piso")) return "Llamada con amenaza y pedido de dinero";
    if (brand.includes("comercio local")) return "Reporte sobre un negocio que aún no se ha revisado";
    if (brand.includes("banco")) return "Mensaje que podría hacerse pasar por un banco";
    if (brand.includes("paqueter")) return "Mensaje sobre un paquete que podría ser engañoso";
    return "Posible engaño en revisión";
  }

  function renderCampaigns(data) {
    const list = document.getElementById("campaigns-list");
    const count = document.getElementById("alert-count");
    list.replaceChildren();
    const campaigns = data.alerts || [];
    count.textContent = campaigns.length
      ? `${campaigns.length} aviso${campaigns.length === 1 ? "" : "s"} en esta demostración`
      : "Por ahora no hay avisos para mostrar.";

    if (!campaigns.length) {
      list.append(make("p", "help-text", "Si recibiste un mensaje sospechoso, puedes revisarlo o reportarlo."));
      return;
    }

    campaigns.forEach((campaign) => {
      const item = make("article", "campaign-item");
      const title = make("h3", "", describeAlert(campaign));
      item.append(title);
      const status = labels[campaign.status] || labels.sin_verificar;
      item.append(make("p", "status-message neutral", status));

      const channels = (campaign.channels || []).map((channel) => labels[channel] || "Reporte");
      if (channels.length) item.append(make("p", "help-text", `Señales recibidas por: ${[...new Set(channels)].join(" y ")}.`));
      item.append(make("p", "help-text", "Antes de actuar, confirma la información con la institución por un canal conocido."));
      list.append(item);
    });
  }

  function pointBounds(geojson) {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    (geojson.features || []).forEach((feature) => {
      const polygons = feature.geometry.type === "MultiPolygon"
        ? feature.geometry.coordinates
        : [feature.geometry.coordinates];
      polygons.forEach((polygon) => polygon.forEach((ring) => ring.forEach(([x, y]) => {
        minX = Math.min(minX, x); maxX = Math.max(maxX, x);
        minY = Math.min(minY, y); maxY = Math.max(maxY, y);
      })));
    });
    return { minX, maxX, minY, maxY };
  }

  function renderMap(mapData) {
    const svg = document.getElementById("qro-map-svg");
    const list = document.getElementById("map-regions");
    const summary = document.getElementById("map-total");
    svg.replaceChildren();
    list.replaceChildren();

    const geojson = mapData.geojson || {};
    const features = geojson.features || [];
    const bounds = pointBounds(geojson);
    const width = 640, height = 520, pad = 24;
    const spanX = Math.max(bounds.maxX - bounds.minX, .001);
    const spanY = Math.max(bounds.maxY - bounds.minY, .001);
    const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
    const offsetX = (width - spanX * scale) / 2;
    const offsetY = (height - spanY * scale) / 2;
    const visible = mapData.visible_areas || [];

    function project([x, y]) {
      return [offsetX + (x - bounds.minX) * scale, height - (offsetY + (y - bounds.minY) * scale)];
    }

    features.forEach((feature) => {
      const polygons = feature.geometry.type === "MultiPolygon"
        ? feature.geometry.coordinates
        : [feature.geometry.coordinates];
      const d = polygons.map((polygon) => polygon.map((ring) => ring.map((point, index) => {
        const [x, y] = project(point);
        return `${index ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`;
      }).join(" ") + " Z").join(" ")).join(" ");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", d);
      path.setAttribute("stroke", "#355347");
      path.setAttribute("stroke-width", "1.5");
      path.setAttribute("fill", feature.properties.published ? "#4b9b70" : "#e1e9e3");
      svg.append(path);
    });

    summary.textContent = visible.length
      ? `${visible.length} zona${visible.length === 1 ? "" : "s"} con avisos suficientes para mostrarse.`
      : "Aún no hay zonas con suficientes avisos para mostrarse.";
    visible.sort((a, b) => b.count - a.count).forEach((region) => {
      list.append(make("li", "", `${region.name}: ${region.count} avisos`));
    });
  }

  async function load() {
    try {
      const [dashboardResponse, mapResponse] = await Promise.all([
        fetch("/api/public/alerts"),
        fetch("/api/public/map"),
      ]);
      if (!dashboardResponse.ok || !mapResponse.ok) throw new Error("No se pudo cargar la información");
      renderCampaigns(await dashboardResponse.json());
      renderMap(await mapResponse.json());
    } catch {
      document.getElementById("alert-count").textContent = "No se pudieron cargar los avisos.";
      document.getElementById("campaigns-list").replaceChildren(
        make("p", "help-text", "Vuelve a intentarlo en un momento o regresa al inicio.")
      );
      document.getElementById("map-total").textContent = "No se pudo cargar la información de zonas.";
    }
  }

  load();
})();
