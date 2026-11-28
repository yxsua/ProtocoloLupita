/* Interacciones accesibles de revisión de mensajes y reportes ciudadanos. */
(function () {
  "use strict";

  function el(id) { return document.getElementById(id); }

  function addText(parent, tag, text, className) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    node.textContent = text;
    parent.append(node);
    return node;
  }

  function renderNextSteps(container) {
    container.replaceChildren();
    addText(container, "h3", "Qué puedes hacer ahora");
    const list = document.createElement("ol");
    list.className = "list-clean";
    [
      "No respondas ni abras enlaces del mensaje.",
      "Verifica la información desde una aplicación o un contacto que ya conozcas.",
      "Si compartiste dinero o información, pide ayuda a una persona de confianza.",
    ].forEach((text) => {
      const item = document.createElement("li");
      item.textContent = text;
      list.append(item);
    });
    container.append(list);
  }

  function setResultWarning(node, text) {
    node.textContent = text || "";
    node.hidden = !text;
  }

  const smsForm = el("sms-analyze-form");
  if (smsForm) {
    smsForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = el("sms-submit");
      const resultCard = el("sms-result-card");
      button.disabled = true;
      button.textContent = "Revisando…";
      try {
        const response = await fetch("/sms/api/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            body: el("sms-body").value,
            sender: el("sms-sender").value,
          }),
        });
        if (!response.ok) throw new Error("No fue posible revisar el mensaje.");
        const data = await response.json();
        resultCard.hidden = false;
        const heading = el("sms-res-status");
        if (data.is_suspicious) {
          heading.textContent = "Detectamos señales de un posible engaño.";
          heading.className = "status-message warning";
        } else {
          heading.textContent = "No encontramos señales claras de engaño.";
          heading.className = "status-message neutral";
        }
        setResultWarning(el("sms-res-warning"), data.is_suspicious
          ? "No respondas ni abras enlaces. La revisión encontró señales que conviene comprobar."
          : "");
        const explanation = (data.explanation || "").trim();
        el("sms-res-explanation").textContent = data.is_suspicious
          ? [explanation, "No abras el enlace ni respondas. Verifica la información por un canal oficial que ya conozcas."].filter(Boolean).join(" ")
          : [explanation, "Esto no garantiza que el mensaje sea seguro. No compartas contraseñas, códigos ni datos de tu cuenta."].filter(Boolean).join(" ");
        renderNextSteps(el("sms-res-advice"));
        resultCard.focus();
      } catch (error) {
        resultCard.hidden = false;
        el("sms-res-status").textContent = "No pudimos revisar el mensaje.";
        el("sms-res-explanation").textContent = error.message || "Vuelve a intentarlo.";
        el("sms-res-advice").replaceChildren();
      } finally {
        button.disabled = false;
        button.textContent = "Revisar mensaje";
      }
    });
  }

  const reportForm = el("citizen-report-form");
  if (reportForm) {
    reportForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = el("report-submit");
      const resultCard = el("citizen-result-card");
      button.disabled = true;
      button.textContent = "Enviando…";
      try {
        const formData = new FormData(reportForm);
        const payload = Object.fromEntries(formData.entries());
        const response = await fetch("/citizen/api/report", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) throw new Error("No pudimos recibir el reporte. Revisa el formulario e inténtalo de nuevo.");
        const data = await response.json();
        resultCard.hidden = false;
        const heading = el("cit-res-status");
        if (data.rate_limited || data.verification_status === "sin_verificar") {
          heading.textContent = "Recibimos tu reporte. Aún no podemos confirmarlo.";
        } else if (data.verification_status === "campana_corroborada") {
          heading.textContent = "El reporte coincide con otras señales. Mantén la precaución.";
        } else {
          heading.textContent = "Recibimos tu reporte. Hay señales que conviene revisar.";
        }
        setResultWarning(el("cit-res-warning"), data.preventive_warning
          ? "Este reporte coincide con otras señales. Mantén la precaución."
          : "");
        el("cit-res-explanation").textContent = "Una coincidencia ayuda a orientar a otras personas, pero no confirma por sí sola que haya ocurrido un fraude.";
        renderNextSteps(el("cit-res-route"));
        resultCard.focus();
      } catch (error) {
        resultCard.hidden = false;
        el("cit-res-status").textContent = "No pudimos recibir el reporte.";
        el("cit-res-explanation").textContent = error.message || "Vuelve a intentarlo.";
        el("cit-res-route").replaceChildren();
      } finally {
        button.disabled = false;
        button.textContent = "Enviar reporte";
      }
    });
  }
})();
