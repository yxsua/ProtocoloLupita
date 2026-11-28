(() => {
  const $ = (id) => document.getElementById(id);
  const select = $("scenario-select");
  const incoming = $("incoming-screen");
  const active = $("active-screen");
  const transcript = $("transcript");
  const status = $("incoming-notice");
  const callStatus = $("call-status");
  const voiceStatus = $("voice-status");
  const answerButton = $("btn-answer");
  const declineButton = $("btn-decline");
  const cancelButton = $("btn-cancel");
  const resetButton = $("btn-reset");
  const resetIncomingButton = $("btn-reset-incoming");
  const recoverButton = $("btn-recover");
  const state = { sessionId: "", running: false, cancelled: false, startedAt: 0, timer: 0, voices: [] };

  async function prepareVoices() {
    if (!("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    state.voices = synth.getVoices();
    if (state.voices.length) return;
    await new Promise((resolve) => {
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        synth.removeEventListener?.("voiceschanged", finish);
        state.voices = synth.getVoices();
        resolve();
      };
      const timeout = window.setTimeout(finish, 1200);
      synth.addEventListener?.("voiceschanged", finish, { once: true });
    });
  }

  function voiceFor(role) {
    const spanish = state.voices.filter((voice) => /^es([-_]|$)/i.test(voice.lang));
    const maleNames = /male|mascul|raul|raúl|jorge|diego|pablo|carlos|juan|miguel|manuel|antonio|alvaro|álvaro|enrique|andres|andrés|gonzalo|sergio|hector|héctor/i;
    const femaleNames = /female|fem|dalia|sabina|lucia|lucía|monica|mónica|paulina|helena|elena|irene|laura|maria|maría|ana|sofia|sofía|eva|camila/i;
    const mexicanSpanish = spanish.filter((voice) => /^es-MX$/i.test(voice.lang));
    const male = mexicanSpanish.find((voice) => maleNames.test(voice.name))
      || spanish.find((voice) => maleNames.test(voice.name));
    const female = mexicanSpanish.find((voice) => femaleNames.test(voice.name))
      || spanish.find((voice) => femaleNames.test(voice.name));
    const base = mexicanSpanish[0] || spanish[0];
    const womanVoice = female || base;
    const manVoice = male || spanish.find((voice) => voice !== womanVoice) || base;
    return role === "atacante" ? manVoice : womanVoice;
  }

  function speak(text, role) {
    if (!text || !("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) {
      voiceStatus.textContent = "La síntesis de voz no está disponible en este navegador; la conversación sigue visible en texto.";
      return Promise.resolve();
    }
    return new Promise((resolve) => {
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "es-MX";
      utterance.voice = voiceFor(role) || null;
      utterance.pitch = role === "atacante" ? 0.58 : 1.38;
      utterance.rate = role === "atacante" ? 1.04 : 0.92;
      utterance.onend = resolve;
      utterance.onerror = resolve;
      voiceStatus.textContent = `Voz sintética ${role === "atacante" ? "masculina · estafador" : "femenina · Doña Lupita"}`;
      window.speechSynthesis.speak(utterance);
    });
  }

  function appendLine(role, text) {
    const bubble = document.createElement("p");
    bubble.className = `message ${role}`;
    bubble.textContent = text;
    transcript.appendChild(bubble);
    transcript.scrollTop = transcript.scrollHeight;
  }

  function startTimer() {
    state.startedAt = Date.now();
    clearInterval(state.timer);
    state.timer = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - state.startedAt) / 1000);
      $("timer").textContent = `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
    }, 500);
  }

  function formBody(fields) {
    const body = new FormData();
    for (const [key, value] of Object.entries(fields)) body.append(key, value);
    return body;
  }

  async function responseData(response) {
    const raw = await response.text();
    let data;
    try { data = raw ? JSON.parse(raw) : {}; }
    catch { throw new Error(`Respuesta no válida del servidor (${response.status}).`); }
    if (!response.ok) {
      const error = new Error(data.detail || `No se pudo completar la llamada (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return data;
  }

  async function loadScenarios() {
    const response = await fetch("/api/gobierno/snapshot", { credentials: "same-origin" });
    const data = await responseData(response);
    select.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Elige un escenario precargado";
    select.appendChild(placeholder);
    for (const scenario of data.scenarios || []) {
      const option = document.createElement("option");
      option.value = scenario.id;
      option.textContent = `${scenario.id} · ${scenario.label}`;
      select.appendChild(option);
    }
    select.disabled = false;
    answerButton.disabled = !select.value;
    status.textContent = select.options.length > 1 ? "Selecciona un escenario y contesta para iniciar la llamada." : "No hay escenarios de llamada disponibles.";
  }

  async function runConversation() {
    state.running = true;
    state.cancelled = false;
    answerButton.disabled = true;
    declineButton.disabled = true;
    select.disabled = true;
    status.textContent = "Contestando la llamada simulada…";
    try {
      await prepareVoices();
      const data = await responseData(await fetch("/voice/scenario/start", {
        method: "POST", credentials: "same-origin", body: formBody({ scenario_id: select.value }),
      }));
      state.sessionId = data.session_id;
      $("active-scenario").textContent = data.scenario_id;
      incoming.classList.add("hidden");
      active.classList.remove("hidden");
      callStatus.textContent = `Llamada conectada · escenario ${data.scenario_id}`;
      appendLine("lupita", data.greeting);
      startTimer();
      await speak(data.greeting, "victima");

      while (!state.cancelled) {
        const turn = await responseData(await fetch("/voice/scenario/next", {
          method: "POST", credentials: "same-origin", body: formBody({ session_id: state.sessionId }),
        }));
        if (turn.finished && !turn.attacker_line) break;
        appendLine("atacante", turn.attacker_line);
        await speak(turn.attacker_line, "atacante");
        if (state.cancelled) break;
        appendLine("lupita", turn.victim_line);
        await speak(turn.victim_line, "victima");
        callStatus.textContent = `Escenario ${turn.scenario_id} · turno ${turn.turn} de ${turn.turn_count}`;
        if (turn.finished) break;
      }

      if (!state.cancelled) {
        callStatus.textContent = "Escenario completado · resultado guardado en el historial gubernamental.";
        voiceStatus.textContent = "Las dos voces sintéticas terminaron la conversación.";
      }
    } catch (error) {
      window.speechSynthesis?.cancel();
      if (!state.sessionId) {
        status.textContent = error.message;
        recoverButton.classList.toggle("hidden", error.status !== 409);
      } else {
        callStatus.textContent = `${error.message} Se cerró la sesión para permitir otro intento.`;
        try {
          await responseData(await fetch("/voice/hangup", {
            method: "POST", credentials: "same-origin", body: formBody({ session_id: state.sessionId }),
          }));
        } catch { /* El servidor pudo cerrar la sesión al reportar el error. */ }
      }
    } finally {
      state.running = false;
      if (!state.sessionId) {
        answerButton.disabled = !select.value;
        declineButton.disabled = false;
        select.disabled = false;
        return;
      }
      clearInterval(state.timer);
      cancelButton.classList.add("hidden");
      resetButton.classList.remove("hidden");
      resetButton.focus();
    }
  }

  async function cancelCall() {
    if (!state.sessionId || state.cancelled) return;
    state.cancelled = true;
    window.speechSynthesis?.cancel();
    cancelButton.disabled = true;
    callStatus.textContent = "Cancelando llamada…";
    try {
      await responseData(await fetch("/voice/hangup", {
        method: "POST", credentials: "same-origin", body: formBody({ session_id: state.sessionId }),
      }));
      callStatus.textContent = "Llamada cancelada · sesión cerrada.";
    } catch (error) {
      callStatus.textContent = error.message;
    }
  }

  async function recoverBlockedCall() {
    recoverButton.disabled = true;
    status.textContent = "Cerrando la sesión anterior…";
    try {
      await responseData(await fetch("/voice/cancel-active", {
        method: "POST", credentials: "same-origin",
      }));
      reset();
      status.textContent = "Sesión anterior cerrada. Elige un escenario para volver a intentarlo.";
    } catch (error) {
      status.textContent = error.message;
    } finally {
      recoverButton.disabled = false;
    }
  }

  function rejectIncoming() {
    incoming.classList.add("rejected");
    status.textContent = "Llamada rechazada. No se inició ninguna sesión.";
    answerButton.disabled = true;
    declineButton.disabled = true;
    select.disabled = true;
    resetIncomingButton.classList.remove("hidden");
  }

  function reset() {
    window.speechSynthesis?.cancel();
    clearInterval(state.timer);
    state.sessionId = "";
    state.running = false;
    state.cancelled = false;
    transcript.replaceChildren();
    transcript.classList.remove("hidden");
    active.querySelector(".active-call-header").classList.remove("hidden");
    active.querySelector(".transcript-heading").classList.remove("hidden");
    active.classList.add("hidden");
    incoming.classList.remove("hidden", "rejected");
    select.disabled = false;
    answerButton.disabled = !select.value;
    declineButton.disabled = false;
    cancelButton.disabled = false;
    cancelButton.classList.remove("hidden");
    resetButton.classList.add("hidden");
    resetIncomingButton.classList.add("hidden");
    recoverButton.classList.add("hidden");
    status.textContent = "Selecciona un escenario y contesta para comenzar.";
    $("timer").textContent = "00:00";
  }

  select.addEventListener("change", () => { answerButton.disabled = !select.value; });
  answerButton.addEventListener("click", runConversation);
  declineButton.addEventListener("click", rejectIncoming);
  cancelButton.addEventListener("click", cancelCall);
  resetButton.addEventListener("click", reset);
  resetIncomingButton.addEventListener("click", reset);
  recoverButton.addEventListener("click", recoverBlockedCall);
  loadScenarios().catch((error) => {
    select.replaceChildren(new Option("No se pudieron cargar los escenarios", ""));
    status.textContent = error.message;
  });
})();
