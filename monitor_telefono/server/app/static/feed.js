(() => {
  "use strict";

  const form = document.getElementById("filters-form");
  const list = document.getElementById("event-list");
  const emptyState = document.getElementById("empty-state");
  const connectionState = document.getElementById("connection-state");
  const feedStatus = document.getElementById("feed-status");
  const loadMoreButton = document.getElementById("load-more");
  const events = new Map();
  let nextCursor = null;
  let socket = null;
  let reconnectTimer = null;
  let loading = false;

  const appNames = {
    "com.whatsapp": "WhatsApp",
    "org.telegram.messenger": "Telegram",
    "com.facebook.orca": "Messenger",
    "com.google.android.apps.messaging": "Mensajes",
    "com.android.messaging": "Mensajes",
    "com.android.phone": "Teléfono",
    "com.google.android.dialer": "Teléfono",
    "org.thoughtcrime.securesms": "Signal",
    "com.instagram.android": "Instagram"
  };
  const typeNames = {
    notificacion: "Notificación",
    sms: "SMS",
    llamada: "Llamada"
  };

  function currentFilters() {
    const data = new FormData(form);
    const params = new URLSearchParams();
    for (const name of ["dispositivo", "app", "tipo", "texto"]) {
      const value = String(data.get(name) || "").trim();
      if (value) params.set(name, value);
    }
    return params;
  }

  function keyFor(event) {
    return event.id_evento || [
      event.dispositivo_id,
      event.app,
      event.fecha,
      event.texto
    ].join("|");
  }

  function eventMatches(event) {
    const filters = currentFilters();
    return (!filters.has("dispositivo") || event.dispositivo_id === filters.get("dispositivo"))
      && (!filters.has("app") || event.app === filters.get("app"))
      && (!filters.has("tipo") || event.tipo === filters.get("tipo"))
      && (!filters.has("texto") || `${event.remitente || ""} ${event.texto || ""}`
        .toLocaleLowerCase()
        .includes(filters.get("texto").toLocaleLowerCase()));
  }

  function formatTime(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "Fecha desconocida";
    return new Intl.DateTimeFormat("es-MX", {
      dateStyle: "medium",
      timeStyle: "medium"
    }).format(date);
  }

  function createEventCard(event) {
    const item = document.createElement("li");
    item.className = "event-card";

    const origin = document.createElement("div");
    origin.className = "event-origin";
    const app = document.createElement("span");
    app.className = "app-name";
    app.textContent = appNames[event.app] || event.app || "Aplicación desconocida";
    const type = document.createElement("span");
    type.className = "event-type";
    type.textContent = typeNames[event.tipo] || "Evento";
    origin.append(app, type);

    const content = document.createElement("div");
    content.className = "event-content";
    if (event.remitente) {
      const sender = document.createElement("p");
      sender.className = "event-sender";
      sender.textContent = event.remitente;
      content.append(sender);
    }
    if (event.texto) {
      const message = document.createElement("p");
      message.textContent = event.texto;
      content.append(message);
    }
    if (event.tipo === "llamada") {
      const callDetails = document.createElement("p");
      const direction = event.direccion ? ` · ${event.direccion}` : "";
      const duration = Number.isInteger(event.duracion_s) ? ` · ${event.duracion_s} s` : "";
      callDetails.textContent = `Detalle de llamada${direction}${duration}`;
      content.append(callDetails);
    }

    const meta = document.createElement("div");
    meta.className = "event-meta";
    const device = document.createElement("p");
    device.textContent = event.dispositivo || "Dispositivo";
    const time = document.createElement("time");
    time.dateTime = event.fecha || "";
    time.textContent = formatTime(event.fecha);
    meta.append(device, time);

    item.append(origin, content, meta);
    return item;
  }

  function render() {
    const ordered = Array.from(events.values()).sort((left, right) => {
      const leftTime = Date.parse(left.recibido_en || left.fecha) || 0;
      const rightTime = Date.parse(right.recibido_en || right.fecha) || 0;
      return rightTime - leftTime;
    });
    list.replaceChildren(...ordered.map(createEventCard));
    emptyState.hidden = ordered.length > 0;
    loadMoreButton.hidden = !nextCursor;
  }

  async function loadHistory(reset) {
    if (loading) return;
    loading = true;
    feedStatus.textContent = "Cargando eventos…";
    if (reset) {
      events.clear();
      nextCursor = null;
      render();
    }
    const params = currentFilters();
    params.set("limit", "50");
    if (!reset && nextCursor) params.set("cursor", nextCursor);
    try {
      const response = await fetch("/api/eventos/buscar", {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
          "X-CSRF-Token": String(new FormData(form).get("csrf_token") || "")
        },
        body: JSON.stringify(Object.fromEntries(params.entries())),
        credentials: "same-origin"
      });
      if (response.status === 401) {
        window.location.assign("/login");
        return;
      }
      if (!response.ok) throw new Error(`Error HTTP ${response.status}`);
      const result = await response.json();
      for (const event of result.items || []) {
        if (eventMatches(event)) events.set(keyFor(event), event);
      }
      nextCursor = result.next_cursor || null;
      feedStatus.textContent = events.size ? "" : "No se encontraron eventos para estos filtros.";
      render();
    } catch (error) {
      feedStatus.textContent = "No se pudo cargar el historial. Revisa la conexión e inténtalo de nuevo.";
      console.error("Error cargando el historial de eventos:", error);
    } finally {
      loading = false;
    }
  }

  function setConnectionState(text, className) {
    connectionState.textContent = text;
    connectionState.classList.remove("is-connected", "is-disconnected");
    if (className) connectionState.classList.add(className);
  }

  function connect() {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return;
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    socket = new WebSocket(`${scheme}//${window.location.host}/ws/eventos`);
    setConnectionState("Conectando…", "");

    socket.addEventListener("open", () => {
      setConnectionState("En vivo", "is-connected");
      loadHistory(true);
    });
    socket.addEventListener("message", (message) => {
      try {
        const event = JSON.parse(message.data);
        if (eventMatches(event)) {
          events.set(keyFor(event), event);
          render();
        }
      } catch (error) {
        console.error("Se recibió un evento WebSocket inválido:", error);
      }
    });
    socket.addEventListener("close", () => {
      setConnectionState("Desconectado · reconectando…", "is-disconnected");
      loadHistory(true);
      window.clearTimeout(reconnectTimer);
      reconnectTimer = window.setTimeout(connect, 2000);
    });
    socket.addEventListener("error", () => {
      setConnectionState("Problema de conexión · reconectando…", "is-disconnected");
    });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    loadHistory(true);
  });
  document.getElementById("clear-filters").addEventListener("click", () => {
    form.reset();
    loadHistory(true);
  });
  loadMoreButton.addEventListener("click", () => loadHistory(false));

  loadHistory(true);
  connect();
})();
