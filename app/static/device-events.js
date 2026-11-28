"use strict";

const MAX_EVENTOS = 200;
const eventos = new Map();
const lista = document.getElementById("lista");
const vacio = document.getElementById("vacio");
const estado = document.getElementById("estado");
const conteo = document.getElementById("conteo-eventos");
const filtros = {
  texto: document.getElementById("filtro-texto"),
  tipo: document.getElementById("filtro-tipo"),
  app: document.getElementById("filtro-app"),
  dispositivo: document.getElementById("filtro-dispositivo"),
  desde: document.getElementById("filtro-desde"),
  hasta: document.getElementById("filtro-hasta"),
};

const nombresApp = {
  "com.whatsapp": "WhatsApp",
  "com.whatsapp.w4b": "WhatsApp Business",
  "org.telegram.messenger": "Telegram",
  "com.facebook.orca": "Messenger",
  "com.instagram.android": "Instagram",
  "com.google.android.apps.messaging": "Mensajes",
  "com.samsung.android.messaging": "Mensajes",
  "com.android.dialer": "Teléfono",
  "com.google.android.dialer": "Teléfono",
  "com.samsung.android.dialer": "Teléfono",
  "com.android.phone": "Teléfono",
  "com.samsung.android.incallui": "Teléfono",
};
const etiquetasTipo = {
  notificacion: "Notificación",
  sms: "SMS",
  llamada: "Llamada",
};
const etiquetasAnalisis = {
  sin_verificar: "Sin verificar",
  indicio: "Indicio en seguimiento",
  campana_corroborada: "Coincidencia con campaña",
};

function crearElemento(tag, clase, texto) {
  const elemento = document.createElement(tag);
  if (clase) elemento.className = clase;
  if (texto !== null && texto !== undefined && texto !== "") {
    elemento.textContent = String(texto);
  }
  return elemento;
}

function normalizar(valor) {
  return String(valor || "").normalize("NFKC").toLocaleLowerCase("es-MX");
}

function sincronizarOpciones(select, valores, etiquetaTodas) {
  const seleccionado = select.value;
  const opciones = [...new Set(valores.filter(Boolean))].sort((a, b) => a.localeCompare(b, "es-MX"));
  select.replaceChildren(new Option(etiquetaTodas, ""));
  for (const valor of opciones) select.add(new Option(nombresApp[valor] || valor, valor));
  if (opciones.includes(seleccionado)) select.value = seleccionado;
}

function coincide(evento) {
  const query = normalizar(filtros.texto.value.trim());
  const analisis = evento.analisis || {};
  const contenido = normalizar([
    evento.texto,
    evento.remitente,
    evento.app,
    nombresApp[evento.app],
    evento.dispositivo,
    analisis.explanation,
    analisis.campaign_name,
    ...(analisis.rule_signals || []),
  ].join(" "));
  const fecha = String(evento.fecha || "").slice(0, 10);
  return (!query || contenido.includes(query)) &&
    (!filtros.tipo.value || evento.tipo === filtros.tipo.value) &&
    (!filtros.app.value || evento.app === filtros.app.value) &&
    (!filtros.dispositivo.value || evento.dispositivo === filtros.dispositivo.value) &&
    (!filtros.desde.value || fecha >= filtros.desde.value) &&
    (!filtros.hasta.value || fecha <= filtros.hasta.value);
}

function crearAnalisis(analisis) {
  const details = document.createElement("details");
  details.className = "event-analysis";
  const status = etiquetasAnalisis[analisis.verification_status] || "Análisis local";
  const confidence = Number.isFinite(Number(analisis.engine_confidence))
    ? ` · ${Math.round(Number(analisis.engine_confidence) * 100)}% confianza`
    : "";
  details.append(crearElemento("summary", "", `${status}${confidence}`));
  if (analisis.explanation) details.append(crearElemento("p", "", analisis.explanation));
  if (analisis.campaign_name) {
    details.append(crearElemento("p", "event-campaign", `Campaña: ${analisis.campaign_name}`));
  }
  if (analisis.rule_signals?.length) {
    details.append(crearElemento("p", "event-signals", `Señales detectadas: ${analisis.rule_signals.join(", ")}`));
  }
  return details;
}

function crearTarjeta(evento) {
  const item = document.createElement("li");
  const header = crearElemento("div", "event-row");
  const appLabel = nombresApp[evento.app] || evento.app || "Aplicación desconocida";
  header.append(
    crearElemento("strong", `event-app${evento.tipo === "llamada" ? " event-call" : ""}`, `${etiquetasTipo[evento.tipo] || "Evento"} · ${appLabel}`),
    crearElemento("time", "event-time", new Date(evento.fecha).toLocaleString("es-MX")),
  );
  item.append(header);

  if (evento.remitente) item.append(crearElemento("div", "event-sender", evento.remitente));
  if (evento.texto) item.append(crearElemento("p", "event-text", evento.texto));
  if (evento.tipo === "llamada") {
    const direccion = { entrante: "Entrante", saliente: "Saliente", perdida: "Perdida" }[evento.direccion];
    const partes = [direccion].filter(Boolean);
    if (evento.duracion_s !== null && evento.duracion_s !== undefined) {
      partes.push(`Duración ${Math.floor(evento.duracion_s / 60)}:${String(evento.duracion_s % 60).padStart(2, "0")}`);
    }
    if (partes.length) item.append(crearElemento("p", "event-text", partes.join(" · ")));
  }
  item.append(crearElemento("div", "event-device", `Dispositivo: ${evento.dispositivo || "Sin nombre"}`));
  if (evento.analisis) item.append(crearAnalisis(evento.analisis));
  return item;
}

function renderizar() {
  sincronizarOpciones(filtros.app, [...eventos.values()].map((evento) => evento.app), "Todas");
  sincronizarOpciones(filtros.dispositivo, [...eventos.values()].map((evento) => evento.dispositivo), "Todos");
  const ordenados = [...eventos.values()].sort((a, b) => Date.parse(b.fecha) - Date.parse(a.fecha));
  const visibles = ordenados.filter(coincide);
  lista.replaceChildren(...visibles.map(crearTarjeta));
  conteo.textContent = `Mostrando ${visibles.length} de ${eventos.size} eventos`;
  vacio.hidden = visibles.length > 0;
  if (eventos.size && !visibles.length) {
    vacio.textContent = "No hay eventos que coincidan con esos filtros. Prueba con otros términos o límpialos.";
  } else if (!eventos.size) {
    vacio.textContent = "Aún no hay eventos. Vincula un teléfono Android o genera una notificación sintética para iniciar la demostración.";
  }
}

function recibirEvento(evento) {
  const id = evento.id_evento || `${evento.dispositivo}|${evento.fecha}|${evento.app}|${evento.texto || ""}`;
  if (eventos.has(id)) return;
  eventos.set(id, evento);
  while (eventos.size > MAX_EVENTOS) eventos.delete(eventos.keys().next().value);
  renderizar();
}

for (const control of Object.values(filtros)) {
  control.addEventListener(control.tagName === "INPUT" && control.type === "search" ? "input" : "change", renderizar);
}
const formularioFiltros = document.getElementById("filtros-eventos");
formularioFiltros.addEventListener("submit", (event) => event.preventDefault());
formularioFiltros.addEventListener("reset", () => window.setTimeout(renderizar));

function conectar() {
  const protocolo = location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocolo}//${location.host}/ws/eventos`);
  socket.onopen = () => {
    estado.textContent = "En vivo";
    estado.dataset.state = "connected";
  };
  socket.onmessage = (mensaje) => {
    try {
      recibirEvento(JSON.parse(mensaje.data));
    } catch {
      estado.textContent = "Se recibió un evento inválido";
      estado.dataset.state = "error";
    }
  };
  socket.onerror = () => socket.close();
  socket.onclose = (cierre) => {
    if (cierre.code === 1008) {
      estado.textContent = "Acceso no autorizado al canal en vivo";
      estado.dataset.state = "error";
      return;
    }
    estado.textContent = "Reconectando…";
    estado.dataset.state = "connecting";
    window.setTimeout(conectar, 2000);
  };
}

renderizar();
conectar();
