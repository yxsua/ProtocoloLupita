(() => {
  "use strict";

  document.querySelectorAll("form[data-confirm]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  document.querySelectorAll("button[data-copy-target]").forEach((button) => {
    button.addEventListener("click", async () => {
      const input = document.getElementById(button.dataset.copyTarget);
      if (!input) return;
      try {
        await navigator.clipboard.writeText(input.value);
        const status = document.getElementById("copy-status");
        if (status) status.textContent = "Copiado al portapapeles.";
      } catch (error) {
        input.focus();
        input.select();
        const copied = document.execCommand("copy");
        const status = document.getElementById("copy-status");
        if (status) {
          status.textContent = copied
            ? "Copiado al portapapeles."
            : "No se pudo copiar. Selecciona y copia el valor manualmente.";
        }
      }
    });
  });

  document.querySelectorAll("time[data-local-time]").forEach((time) => {
    const date = new Date(time.dataset.localTime);
    if (!Number.isNaN(date.getTime())) {
      time.textContent = new Intl.DateTimeFormat("es-MX", {
        dateStyle: "medium",
        timeStyle: "short"
      }).format(date);
    }
  });

  const refreshState = document.getElementById("device-refresh-state");
  const refreshDeviceStatuses = async () => {
    try {
      const response = await fetch("/api/dispositivos/estado", {
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (!response.ok) {
        if (refreshState) refreshState.textContent = "No se pudo actualizar el estado de conexión.";
        return;
      }
      const payload = await response.json();
      for (const device of payload.dispositivos || []) {
        const row = Array.from(document.querySelectorAll("tr[data-device-id]"))
          .find((item) => item.dataset.deviceId === device.id);
        if (!row) continue;
        const status = row.querySelector("[data-device-connectivity]");
        if (status) {
          status.classList.toggle("status-online", Boolean(device.en_linea));
          status.classList.toggle("status-offline", !device.en_linea);
          status.textContent = device.en_linea ? "En línea" : "Sin conexión";
        }
        const lastContact = row.querySelector("time[data-local-time]");
        if (lastContact) {
          lastContact.dataset.localTime = device.ultimo_contacto || "";
          const date = device.ultimo_contacto
            ? new Date(device.ultimo_contacto)
            : new Date(Number.NaN);
          lastContact.textContent = Number.isNaN(date.getTime())
            ? "Nunca"
            : new Intl.DateTimeFormat("es-MX", {
              dateStyle: "medium",
              timeStyle: "short"
            }).format(date);
        }
      }
      if (refreshState) refreshState.textContent = "Estado actualizado.";
    } catch (error) {
      if (refreshState) refreshState.textContent = "No se pudo actualizar el estado de conexión.";
    }
  };
  refreshDeviceStatuses();
  window.setInterval(refreshDeviceStatuses, 30000);
})();
