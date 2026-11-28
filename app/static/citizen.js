/* Interaccion segura para Bandeja SMS y Portal Ciudadano.
 * Reglas: nunca usar innerHTML con datos no confiables, nunca abrir URLs externas.
 */
(function () {
  "use strict";

  function clearNode(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function renderDefangedUrls(container, urls) {
    clearNode(container);
    if (!urls || urls.length === 0) return;

    const title = document.createElement("p");
    title.textContent = "Enlaces extraidos (desactivados y no abiertos):";
    container.appendChild(title);

    urls.forEach(function (url) {
      const row = document.createElement("div");
      row.style.marginBottom = "0.4rem";

      const code = document.createElement("span");
      code.className = "defanged-url";
      code.textContent = url;

      const badge = document.createElement("span");
      badge.className = "badge";
      badge.style.marginLeft = "0.4rem";
      badge.textContent = "No abierto · hxxp";

      row.appendChild(code);
      row.appendChild(badge);
      container.appendChild(row);
    });
  }

  function renderCircularMatches(container, matches) {
    clearNode(container);
    if (!matches || matches.length === 0) return;

    const heading = document.createElement("h4");
    heading.textContent = "Coincidencias de analisis circular";
    container.appendChild(heading);

    const ul = document.createElement("ul");
    matches.forEach(function (m) {
      const li = document.createElement("li");
      const pct = Math.round((m.similarity || 0) * 100);
      li.textContent =
        "[" + m.source + " · similitud " + pct + "%] " + m.warning;
      ul.appendChild(li);
    });
    container.appendChild(ul);
  }

  function renderGuidedRoute(container, route) {
    clearNode(container);
    if (!route) return;

    const heading = document.createElement("h4");
    heading.textContent = "Ruta guiada de respuesta";
    container.appendChild(heading);

    const summary = document.createElement("p");
    summary.textContent = route.summary;
    container.appendChild(summary);

    if (route.do_not_actions && route.do_not_actions.length > 0) {
      const warnList = document.createElement("ul");
      route.do_not_actions.forEach(function (item) {
        const li = document.createElement("li");
        li.textContent = item;
        warnList.appendChild(li);
      });
      container.appendChild(warnList);
    }

    if (route.steps && route.steps.length > 0) {
      const stepsList = document.createElement("ol");
      route.steps.forEach(function (step) {
        const li = document.createElement("li");
        const strong = document.createElement("strong");
        strong.textContent = step.title + ": ";
        li.appendChild(strong);
        li.appendChild(document.createTextNode(step.detail));
        if (step.official_channel) {
          const ch = document.createElement("div");
          ch.style.fontSize = "0.85rem";
          ch.style.color = "#334155";
          ch.textContent = "Canal oficial: " + step.official_channel;
          li.appendChild(ch);
        }
        stepsList.appendChild(li);
      });
      container.appendChild(stepsList);
    }
  }

  async function refreshCircularAlertsList(listElementId) {
    const listEl = document.getElementById(listElementId);
    if (!listEl) return;
    const res = await fetch("/sms/api/alerts");
    const payload = await res.json();
    clearNode(listEl);

    if (payload.alerts && payload.alerts.length > 0) {
      payload.alerts.forEach(function (alert) {
        const li = document.createElement("li");
        li.textContent =
          alert.impersonated_entity +
          " (" + alert.report_count + " reporte(s)): " +
          alert.safe_excerpt;
        listEl.appendChild(li);
      });
    } else {
      const li = document.createElement("li");
      li.textContent = "Aun no hay alertas ciudadanas nuevas en esta sesion.";
      listEl.appendChild(li);
    }
  }

  // Bandeja SMS: cargar fixture en formulario, refrescar bandeja en vivo y analizar SMS pegado
  const smsForm = document.getElementById("sms-analyze-form");
  if (smsForm) {
    function bindInboxLoadButtons(root) {
      root.querySelectorAll(".js-load-sms").forEach(function (btn) {
        btn.addEventListener("click", function () {
          document.getElementById("sms-sender").value = btn.dataset.sender || "";
          document.getElementById("sms-municipality").value = btn.dataset.municipality || "";
          document.getElementById("sms-body").value = btn.dataset.body || "";
          smsForm.requestSubmit();
        });
      });
    }

    async function refreshSmsInbox() {
      const listEl = document.getElementById("sms-inbox-list");
      if (!listEl) return;
      const res = await fetch("/sms/api/inbox");
      const data = await res.json();
      clearNode(listEl);

      (data.items || []).forEach(function (entry) {
        const raw = entry.raw || {};
        const analysis = entry.analysis || {};
        const card = document.createElement("article");
        card.className = "card";

        const header = document.createElement("div");
        header.style.display = "flex";
        header.style.justifyContent = "space-between";
        header.style.alignItems = "center";
        header.style.gap = "0.5rem";

        const title = document.createElement("strong");
        const prefix = entry.source === "dispositivo" ? "[En vivo] " : "";
        title.textContent = prefix + (raw.message_id || "") + " · Remitente: " + (raw.sender || "");

        const badge = document.createElement("span");
        if (analysis.verification_status === "campana_corroborada") {
          badge.className = "badge badge-danger";
          badge.textContent = "Campana corroborada";
        } else if (analysis.is_suspicious) {
          badge.className = "badge badge-warn";
          badge.textContent = "Indicio / Sospechoso";
        } else {
          badge.className = "badge badge-muted";
          badge.textContent = "Sin verificar / Informativo";
        }

        header.appendChild(title);
        header.appendChild(badge);
        card.appendChild(header);

        const bodyP = document.createElement("p");
        bodyP.style.margin = "0.5rem 0";
        bodyP.style.color = "#334155";
        bodyP.textContent = raw.body || "";
        card.appendChild(bodyP);

        const metaP = document.createElement("p");
        metaP.style.fontSize = "0.875rem";
        metaP.style.color = "#475569";
        const pct = Math.round((analysis.engine_confidence || 0) * 100);
        metaP.textContent =
          "Entidad: " + (analysis.impersonated_entity || "") +
          " · Tipo: " + (analysis.scam_type || "") +
          " · Confianza motor: " + pct + "%";
        card.appendChild(metaP);

        const urls = (analysis.indicators && analysis.indicators.defanged_urls) || [];
        if (urls.length > 0) {
          const urlWrap = document.createElement("div");
          urls.forEach(function (u) {
            const code = document.createElement("span");
            code.className = "defanged-url";
            code.textContent = u;
            const uBadge = document.createElement("span");
            uBadge.className = "badge badge-muted";
            uBadge.style.marginLeft = "0.35rem";
            uBadge.textContent = "Enlace desactivado · No abierto";
            urlWrap.appendChild(code);
            urlWrap.appendChild(uBadge);
          });
          card.appendChild(urlWrap);
        }

        const btnWrap = document.createElement("div");
        btnWrap.style.marginTop = "0.75rem";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "secondary js-load-sms";
        btn.dataset.sender = raw.sender || "";
        btn.dataset.municipality = raw.municipality || "";
        btn.dataset.body = raw.body || "";
        btn.textContent = "Analizar en detalle";
        btnWrap.appendChild(btn);
        card.appendChild(btnWrap);

        listEl.appendChild(card);
      });

      bindInboxLoadButtons(listEl);
    }

    bindInboxLoadButtons(document);

    const refreshBtn = document.getElementById("refresh-inbox-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", refreshSmsInbox);
    }
    setInterval(refreshSmsInbox, 5000);

    smsForm.addEventListener("submit", async function (evt) {
      evt.preventDefault();
      const payload = {
        sender: document.getElementById("sms-sender").value,
        municipality: document.getElementById("sms-municipality").value,
        body: document.getElementById("sms-body").value,
      };
      const res = await fetch("/sms/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      const card = document.getElementById("sms-result-card");
      card.classList.remove("hidden");

      const warnEl = document.getElementById("sms-res-warning");
      if (warnEl) warnEl.textContent = data.preventive_warning || "";

      const pct = Math.round((data.engine_confidence || 0) * 100);
      document.getElementById("sms-res-status").textContent =
        "Entidad: " + data.impersonated_entity +
        " | Tipo: " + data.scam_type +
        " | Estado: " + data.verification_status +
        " (confianza motor: " + pct + "%)";
      document.getElementById("sms-res-explanation").textContent = data.explanation || "";

      renderCircularMatches(
        document.getElementById("sms-res-circular"),
        data.circular_matches || []
      );
      renderDefangedUrls(
        document.getElementById("sms-res-urls"),
        (data.indicators && data.indicators.defanged_urls) || []
      );

      const indContainer = document.getElementById("sms-res-indicators");
      clearNode(indContainer);
      const phones = (data.indicators && data.indicators.phones) || [];
      const accounts = (data.indicators && data.indicators.accounts) || [];
      if (phones.length > 0 || accounts.length > 0) {
        const p = document.createElement("p");
        p.textContent =
          "Indicadores extraidos — Telefonos: " + (phones.join(", ") || "ninguno") +
          " | Cuentas: " + (accounts.join(", ") || "ninguna");
        indContainer.appendChild(p);
      }

      renderGuidedRoute(document.getElementById("sms-res-route"), data.guided_route);
    });
  }

  // Portal Ciudadano: enviar reporte saneado y refrescar agregados municipales y alertas circulares
  const citizenForm = document.getElementById("citizen-report-form");
  if (citizenForm) {
    async function refreshMapAggregates() {
      const res = await fetch("/citizen/api/map-aggregates");
      const agg = await res.json();
      const totalEl = document.getElementById("map-total-reports");
      if (totalEl) totalEl.textContent = String(agg.total_reports || 0);

      const listEl = document.getElementById("map-municipalities-list");
      if (listEl) {
        clearNode(listEl);
        if (agg.visible_municipalities && agg.visible_municipalities.length > 0) {
          agg.visible_municipalities.forEach(function (item) {
            const li = document.createElement("li");
            li.textContent = item.municipality + ": " + item.count + " reportes";
            listEl.appendChild(li);
          });
        } else {
          const li = document.createElement("li");
          li.textContent =
            "Ningun municipio alcanza aun el umbral minimo de " + agg.threshold + " reportes.";
          listEl.appendChild(li);
        }
      }
    }

    citizenForm.addEventListener("submit", async function (evt) {
      evt.preventDefault();
      const formData = new FormData(citizenForm);
      const payload = {};
      formData.forEach(function (val, key) {
        if (String(val).trim() !== "") {
          payload[key] = String(val);
        }
      });

      const res = await fetch("/citizen/api/report", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();

      const card = document.getElementById("citizen-result-card");
      card.classList.remove("hidden");

      const warnEl = document.getElementById("cit-res-warning");
      if (warnEl) warnEl.textContent = data.preventive_warning || "";

      const pct = Math.round((data.engine_confidence || 0) * 100);
      document.getElementById("cit-res-status").textContent =
        "Folio: " + data.report_id +
        " | Estado: " + data.verification_status +
        " | Limite de tasa: " + (data.rate_limited ? "Si" : "No") +
        " | Comercio publicado: " + (data.business_published ? "Si" : "No") +
        " (confianza motor: " + pct + "%)";
      document.getElementById("cit-res-explanation").textContent = data.explanation || "";

      const discarded = (data.discarded_pii_fields || []).concat(data.redacted_inline_pii || []);
      document.getElementById("cit-res-pii").textContent =
        discarded.length > 0
          ? "Datos personales descartados antes de guardar: " + discarded.join(", ")
          : "Sin datos personales detectados en el formulario.";

      renderCircularMatches(
        document.getElementById("cit-res-circular"),
        data.circular_matches || []
      );
      renderDefangedUrls(
        document.getElementById("cit-res-urls"),
        (data.indicators && data.indicators.defanged_urls) || []
      );
      renderGuidedRoute(document.getElementById("cit-res-route"), data.guided_route);

      await refreshMapAggregates();
      await refreshCircularAlertsList("citizen-circular-alerts-list");
    });
  }
})();
